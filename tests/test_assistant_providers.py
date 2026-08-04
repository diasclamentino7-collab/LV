from __future__ import annotations

import httpx
import pytest

from app.services import assistant_providers as providers
from app.services.assistant_providers import AssistantError, send_chat_message


def test_missing_api_key_is_rejected_before_any_call() -> None:
    with pytest.raises(AssistantError, match="ChatGPT"):
        send_chat_message("openai", "", "gpt-4o-mini", "system", [])


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(AssistantError):
        send_chat_message("made-up", "key", "model", "system", [])


def test_openai_success_parses_reply(monkeypatch) -> None:
    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == "https://api.openai.com/v1/chat/completions"
        assert headers["Authorization"] == "Bearer sk-test"
        assert json["messages"][0] == {"role": "system", "content": "system"}
        return httpx.Response(200, json={"choices": [{"message": {"content": " Olá! "}}]})

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    reply = send_chat_message("openai", "sk-test", "gpt-4o-mini", "system", [])
    assert reply == "Olá!"


def test_openai_http_error_status_raises_assistant_error(monkeypatch) -> None:
    monkeypatch.setattr(
        providers.httpx, "post", lambda *args, **kwargs: httpx.Response(500, json={"error": "boom"})
    )
    with pytest.raises(AssistantError, match="ChatGPT"):
        send_chat_message("openai", "sk-test", "gpt-4o-mini", "system", [])


def test_openai_network_failure_raises_assistant_error(monkeypatch) -> None:
    def raise_network_error(*args, **kwargs):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(providers.httpx, "post", raise_network_error)
    with pytest.raises(AssistantError, match="ChatGPT"):
        send_chat_message("openai", "sk-test", "gpt-4o-mini", "system", [])


def test_gemini_success_parses_reply(monkeypatch) -> None:
    def fake_post(url, params=None, json=None, timeout=None):
        assert params == {"key": "gem-test"}
        assert json["systemInstruction"] == {"parts": [{"text": "system"}]}
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "Olá do Gemini"}]}}]},
        )

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    reply = send_chat_message("gemini", "gem-test", "gemini-2.0-flash", "system", [])
    assert reply == "Olá do Gemini"


def test_gemini_malformed_response_raises_assistant_error(monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        return httpx.Response(200, json={})

    monkeypatch.setattr(providers.httpx, "post", fake_post)
    with pytest.raises(AssistantError, match="Gemini"):
        send_chat_message("gemini", "gem-test", "gemini-2.0-flash", "system", [])
