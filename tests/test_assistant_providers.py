from __future__ import annotations

from types import SimpleNamespace

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


def test_anthropic_success_reads_text_block(monkeypatch) -> None:
    captured = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                stop_reason="end_turn",
                content=[SimpleNamespace(type="text", text="Olá do Claude")],
            )

    class FakeClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.messages = FakeMessages()

    fake_anthropic_module = SimpleNamespace(
        Anthropic=FakeClient,
        NotFoundError=Exception,
        RateLimitError=Exception,
        APIStatusError=Exception,
        APIConnectionError=Exception,
    )
    monkeypatch.setitem(__import__("sys").modules, "anthropic", fake_anthropic_module)

    reply = send_chat_message("anthropic", "sk-ant-test", "claude-opus-5", "system", [])
    assert reply == "Olá do Claude"
    assert captured["api_key"] == "sk-ant-test"
    assert captured["system"] == "system"


def test_anthropic_refusal_raises_assistant_error(monkeypatch) -> None:
    class FakeMessages:
        def create(self, **kwargs):
            return SimpleNamespace(stop_reason="refusal", content=[])

    class FakeClient:
        def __init__(self, api_key):
            self.messages = FakeMessages()

    fake_anthropic_module = SimpleNamespace(
        Anthropic=FakeClient,
        NotFoundError=Exception,
        RateLimitError=Exception,
        APIStatusError=Exception,
        APIConnectionError=Exception,
    )
    monkeypatch.setitem(__import__("sys").modules, "anthropic", fake_anthropic_module)

    with pytest.raises(AssistantError, match="Claude"):
        send_chat_message("anthropic", "sk-ant-test", "claude-opus-5", "system", [])
