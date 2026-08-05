"""Thin, provider-specific adapters that turn a chat turn into plain text.

Each function takes the same shape (api key, model, system prompt, message
history) and returns the assistant's reply as a plain string, or raises
``AssistantError`` with a message safe to show the couple. No provider SDK
or HTTP detail leaks past this module.
"""

from __future__ import annotations

import httpx

PROVIDERS = ("groq",)
PROVIDER_LABELS = {"groq": "Groq"}
REQUEST_TIMEOUT_SECONDS = 30.0
MAX_REPLY_TOKENS = 700


class AssistantError(Exception):
    """A user-facing, provider-agnostic assistant failure."""


def send_chat_message(
    provider: str,
    api_key: str,
    model: str,
    system_prompt: str,
    history: list[dict[str, str]],
) -> str:
    if not api_key:
        label = PROVIDER_LABELS.get(provider, provider)
        raise AssistantError(f"A chave da API do {label} ainda não está configurada.")
    if provider == "groq":
        return _send_groq(api_key, model, system_prompt, history)
    raise AssistantError("Assistente desconhecido.")


def _send_groq(
    api_key: str, model: str, system_prompt: str, history: list[dict[str, str]]
) -> str:
    messages = [{"role": "system", "content": system_prompt}, *history]
    try:
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": messages,
                "max_tokens": MAX_REPLY_TOKENS,
                "temperature": 0.4,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as error:
        raise AssistantError("Não foi possível contactar o Groq. Tentem novamente.") from error
    if response.status_code >= 400:
        raise AssistantError("O Groq não conseguiu responder. Tentem novamente em instantes.")
    try:
        return response.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise AssistantError("Resposta inesperada do Groq.") from error
