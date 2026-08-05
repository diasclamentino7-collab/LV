from __future__ import annotations

import httpx
import pytest

from app.services import assistant_providers as providers
from app.services.assistant_providers import AssistantError, send_chat_message


def test_missing_api_key_is_rejected_before_any_call() -> None:
    with pytest.raises(AssistantError, match="Groq"):
        send_chat_message("groq", "", "llama-3.3-70b-versatile", "system", [])


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(AssistantError):
        send_chat_message("made-up", "key", "model", "system", [])


def test_groq_success_parses_reply(monkeypatch) -> None:
    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == "https://api.groq.com/openai/v1/chat/completions"
        assert headers["Authorization"] == "Bearer groq-test"
        assert json["messages"][0] == {"role": "system", "content": "system"}
        return httpx.Response(200, json={"choices": [{"message": {"content": " Olá! "}}]})

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    reply = send_chat_message("groq", "groq-test", "llama-3.3-70b-versatile", "system", [])
    assert reply == "Olá!"


def test_groq_http_error_status_raises_assistant_error(monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        return httpx.Response(500, json={"error": "boom"})

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    with pytest.raises(AssistantError, match="Groq"):
        send_chat_message("groq", "groq-test", "llama-3.3-70b-versatile", "system", [])


def test_groq_network_failure_raises_assistant_error(monkeypatch) -> None:
    def raise_network_error(*args, **kwargs):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(providers.httpx, "post", raise_network_error)
    with pytest.raises(AssistantError, match="Groq"):
        send_chat_message("groq", "groq-test", "llama-3.3-70b-versatile", "system", [])


def test_groq_malformed_response_raises_assistant_error(monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        return httpx.Response(200, json={})

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    with pytest.raises(AssistantError, match="Groq"):
        send_chat_message("groq", "groq-test", "llama-3.3-70b-versatile", "system", [])
