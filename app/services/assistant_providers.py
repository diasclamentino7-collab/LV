"""Thin, provider-specific adapters that turn a chat turn into plain text.

Each function takes the same shape (api key, model, system prompt, message
history) and returns the assistant's reply as a plain string, or raises
``AssistantError`` with a message safe to show the couple. No provider SDK
or HTTP detail leaks past this module.
"""

from __future__ import annotations

import httpx

PROVIDERS = ("openai", "anthropic", "gemini")
PROVIDER_LABELS = {"openai": "ChatGPT", "anthropic": "Claude", "gemini": "Gemini"}
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
    if provider == "openai":
        return _send_openai(api_key, model, system_prompt, history)
    if provider == "anthropic":
        return _send_anthropic(api_key, model, system_prompt, history)
    if provider == "gemini":
        return _send_gemini(api_key, model, system_prompt, history)
    raise AssistantError("Assistente desconhecido.")


def _send_openai(
    api_key: str, model: str, system_prompt: str, history: list[dict[str, str]]
) -> str:
    messages = [{"role": "system", "content": system_prompt}, *history]
    try:
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
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
        raise AssistantError("Não foi possível contactar o ChatGPT. Tentem novamente.") from error
    if response.status_code >= 400:
        raise AssistantError("O ChatGPT não conseguiu responder. Tentem novamente em instantes.")
    try:
        return response.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise AssistantError("Resposta inesperada do ChatGPT.") from error


def _send_anthropic(
    api_key: str, model: str, system_prompt: str, history: list[dict[str, str]]
) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=MAX_REPLY_TOKENS,
            system=system_prompt,
            messages=history,
        )
    except anthropic.NotFoundError as error:
        raise AssistantError("O modelo do Claude configurado não foi encontrado.") from error
    except anthropic.RateLimitError as error:
        raise AssistantError(
            "O Claude está com muitos pedidos neste momento. Tentem novamente."
        ) from error
    except anthropic.APIStatusError as error:
        raise AssistantError(
            "O Claude não conseguiu responder. Tentem novamente em instantes."
        ) from error
    except anthropic.APIConnectionError as error:
        raise AssistantError("Não foi possível contactar o Claude. Tentem novamente.") from error
    if response.stop_reason == "refusal":
        raise AssistantError("O Claude não conseguiu responder a este pedido.")
    for block in response.content:
        if block.type == "text":
            return block.text.strip()
    raise AssistantError("Resposta inesperada do Claude.")


def _send_gemini(
    api_key: str, model: str, system_prompt: str, history: list[dict[str, str]]
) -> str:
    contents = [
        {
            "role": "model" if message["role"] == "assistant" else "user",
            "parts": [{"text": message["content"]}],
        }
        for message in history
    ]
    try:
        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": api_key},
            json={
                "contents": contents,
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "generationConfig": {
                    "maxOutputTokens": MAX_REPLY_TOKENS,
                    "temperature": 0.4,
                },
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as error:
        raise AssistantError("Não foi possível contactar o Gemini. Tentem novamente.") from error
    if response.status_code >= 400:
        raise AssistantError("O Gemini não conseguiu responder. Tentem novamente em instantes.")
    try:
        return response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise AssistantError("Resposta inesperada do Gemini.") from error
