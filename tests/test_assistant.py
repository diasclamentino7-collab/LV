from __future__ import annotations

import re

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.templating as templating_module
import app.models  # noqa: F401
import app.routes.assistant as assistant_routes
import app.routes.auth as auth_routes
from app.db.base import Base
from app.main import app
from app.models.assistant import AssistantMessage
from app.models.core import Activity, User
from app.models.planning import Guest
from app.services import assistant_providers
from app.services.assistant_providers import AssistantError
from app.services.security import hash_password


class FakeSettings:
    groq_api_key = "test-groq-key"
    groq_model = "llama-3.3-70b-versatile"


class UnconfiguredSettings(FakeSettings):
    groq_api_key = ""


def csrf_from(page: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', page)
    assert match
    return match.group(1)


def assistant_client(monkeypatch, settings=None):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine)
    monkeypatch.setattr(assistant_routes, "SessionLocal", test_session)
    monkeypatch.setattr(auth_routes, "SessionLocal", test_session)
    monkeypatch.setattr(templating_module, "SessionLocal", test_session)
    monkeypatch.setattr(assistant_routes, "get_settings", lambda: settings or FakeSettings())

    with Session(engine) as db:
        user = User(name="Vítor", password_hash=hash_password("password123"))
        db.add(user)
        db.commit()
        user_id = user.id
    return TestClient(app), test_session, user_id


def add_second_user(test_session: sessionmaker) -> int:
    # Deliberately not named "Leonor": that name triggers the separate
    # love-confirmation login step (see test_auth_experience.py), which is
    # unrelated to what this test is checking.
    with test_session() as db:
        user = User(name="Ana", password_hash=hash_password("password123"))
        db.add(user)
        db.commit()
        return user.id


def login(client: TestClient, user_id: int) -> None:
    page = client.get("/login")
    response = client.post(
        "/login",
        data={
            "user_id": user_id,
            "password": "password123",
            "csrf_token": csrf_from(page.text),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_unconfigured_provider_is_rejected_before_any_network_call(monkeypatch) -> None:
    client, test_session, user_id = assistant_client(monkeypatch, settings=UnconfiguredSettings())

    def unexpected_call(*args, **kwargs):
        raise AssertionError("no provider should be called when the key is missing")

    monkeypatch.setattr(assistant_routes, "send_chat_message", unexpected_call)

    with client:
        login(client, user_id)
        page = client.get("/dashboard")
        response = client.post(
            "/api/assistant/messages",
            data={
                "provider": "groq",
                "content": "Quanto orçamento resta?",
                "csrf_token": csrf_from(page.text),
            },
        )
        assert response.status_code == 503
        assert "Groq" in response.json()["message"]

    with test_session() as db:
        assert db.scalars(select(AssistantMessage)).first() is None


def test_send_message_persists_conversation_and_calls_the_selected_provider(monkeypatch) -> None:
    client, test_session, user_id = assistant_client(monkeypatch)

    calls = []

    def fake_send(provider, api_key, model, system_prompt, history, **kwargs):
        calls.append(
            {
                "provider": provider,
                "api_key": api_key,
                "model": model,
                "system_prompt": system_prompt,
                "history": history,
            }
        )
        return "O orçamento restante é 4200 EUR."

    monkeypatch.setattr(assistant_routes, "send_chat_message", fake_send)

    with client:
        login(client, user_id)
        page = client.get("/dashboard")
        token = csrf_from(page.text)

        response = client.post(
            "/api/assistant/messages",
            data={
                "provider": "groq",
                "content": "Quanto orçamento resta?",
                "csrf_token": token,
            },
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["ok"] is True
        assert payload["user_message"]["content"] == "Quanto orçamento resta?"
        assert payload["assistant_message"]["content"] == "O orçamento restante é 4200 EUR."
        assert payload["assistant_message"]["provider"] == "groq"

        assert len(calls) == 1
        assert calls[0]["provider"] == "groq"
        assert calls[0]["api_key"] == "test-groq-key"
        assert calls[0]["model"] == "llama-3.3-70b-versatile"
        assert "Casal:" in calls[0]["system_prompt"]
        assert calls[0]["history"][-1] == {"role": "user", "content": "Quanto orçamento resta?"}

        history_response = client.get("/api/assistant/messages?provider=groq")
        assert history_response.status_code == 200
        messages = history_response.json()["messages"]
        assert [m["role"] for m in messages] == ["user", "assistant"]

    with test_session() as db:
        stored = db.scalars(select(AssistantMessage)).all()
        assert len(stored) == 2
        assert {row.provider for row in stored} == {"groq"}


def test_provider_failure_keeps_the_users_message_but_adds_no_reply(monkeypatch) -> None:
    client, test_session, user_id = assistant_client(monkeypatch)

    def failing_send(*args, **kwargs):
        raise AssistantError("O Groq não conseguiu responder. Tentem novamente em instantes.")

    monkeypatch.setattr(assistant_routes, "send_chat_message", failing_send)

    with client:
        login(client, user_id)
        page = client.get("/dashboard")
        response = client.post(
            "/api/assistant/messages",
            data={"provider": "groq", "content": "Olá", "csrf_token": csrf_from(page.text)},
        )
        assert response.status_code == 502
        assert "Groq" in response.json()["message"]

    with test_session() as db:
        # The couple's own message is never lost, even when the assistant
        # itself fails to reply — only a matching assistant reply is absent.
        stored = db.scalars(select(AssistantMessage)).all()
        assert [row.role for row in stored] == ["user"]
        assert stored[0].content == "Olá"


def test_unknown_provider_and_missing_csrf_are_rejected(monkeypatch) -> None:
    client, test_session, user_id = assistant_client(monkeypatch)

    with client:
        login(client, user_id)
        page = client.get("/dashboard")
        token = csrf_from(page.text)

        unknown = client.post(
            "/api/assistant/messages",
            data={"provider": "made-up", "content": "Olá", "csrf_token": token},
        )
        assert unknown.status_code == 404

        no_csrf = client.post(
            "/api/assistant/messages",
            data={"provider": "groq", "content": "Olá"},
        )
        assert no_csrf.status_code == 403


def test_each_user_gets_their_own_private_conversation(monkeypatch) -> None:
    client, test_session, vitor_id = assistant_client(monkeypatch)
    ana_id = add_second_user(test_session)

    monkeypatch.setattr(
        assistant_routes, "send_chat_message", lambda *args, **kwargs: "resposta"
    )

    with client:
        login(client, vitor_id)
        page = client.get("/dashboard")
        client.post(
            "/api/assistant/messages",
            data={
                "provider": "groq",
                "content": "Mensagem do Vítor",
                "csrf_token": csrf_from(page.text),
            },
        )

        # Logging in as Ana replaces the session outright (login() itself
        # clears any prior session), no explicit logout needed.
        login(client, ana_id)
        page = client.get("/dashboard")
        ana_history = client.get("/api/assistant/messages?provider=groq").json()["messages"]
        assert ana_history == []

        client.post(
            "/api/assistant/messages",
            data={
                "provider": "groq",
                "content": "Mensagem da Ana",
                "csrf_token": csrf_from(page.text),
            },
        )
        ana_history = client.get("/api/assistant/messages?provider=groq").json()["messages"]
        assert [m["content"] for m in ana_history] == ["Mensagem da Ana", "resposta"]

        login(client, vitor_id)
        vitor_history = client.get("/api/assistant/messages?provider=groq").json()["messages"]
        assert [m["content"] for m in vitor_history] == ["Mensagem do Vítor", "resposta"]


def test_assistant_can_actually_add_a_guest_end_to_end(monkeypatch) -> None:
    """Exercises the real tool loop and the real tool executors together."""
    client, test_session, user_id = assistant_client(monkeypatch)

    groq_responses = [
        httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "add_guest",
                                        "arguments": '{"name": "Bruna", "side": "Noiva"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
        ),
        httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Adicionei a Bruna como convidada."}}]},
        ),
    ]

    def counting_fake_post(url, headers=None, json=None, timeout=None):
        response = groq_responses[counting_fake_post.calls]  # type: ignore[attr-defined]
        counting_fake_post.calls += 1
        return response

    counting_fake_post.calls = 0
    monkeypatch.setattr(assistant_providers.httpx, "post", counting_fake_post)

    with client:
        login(client, user_id)
        page = client.get("/dashboard")
        response = client.post(
            "/api/assistant/messages",
            data={
                "provider": "groq",
                "content": "Adiciona a Bruna como convidada da parte da noiva",
                "csrf_token": csrf_from(page.text),
            },
        )
        assert response.status_code == 201
        reply = response.json()["assistant_message"]["content"]
        assert reply == "Adicionei a Bruna como convidada."

    with test_session() as db:
        guest = db.scalar(select(Guest).where(Guest.name == "Bruna"))
        assert guest is not None
        assert guest.side == "Noiva"
        assert guest.created_by_id == user_id

        activity = db.scalar(
            select(Activity).where(Activity.description.ilike("%Bruna%"))
        )
        assert activity is not None
        assert activity.user_id == user_id
