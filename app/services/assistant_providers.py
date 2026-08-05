"""Thin, provider-specific adapters that turn a chat turn into plain text.

Each function takes the same shape (api key, model, system prompt, message
history, optional tools) and returns the assistant's reply as a plain
string, or raises ``AssistantError`` with a message safe to show the
couple. No provider SDK or HTTP detail leaks past this module.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

PROVIDERS = ("groq",)
PROVIDER_LABELS = {"groq": "Groq"}
REQUEST_TIMEOUT_SECONDS = 30.0
MAX_REPLY_TOKENS = 900
MAX_TOOL_ROUNDS = 6

ToolExecutor = Callable[[str, dict[str, Any]], dict[str, Any]]


class AssistantError(Exception):
    """A user-facing, provider-agnostic assistant failure."""


def send_chat_message(
    provider: str,
    api_key: str,
    model: str,
    system_prompt: str,
    history: list[dict[str, str]],
    *,
    tools: list[dict[str, Any]] | None = None,
    execute_tool: ToolExecutor | None = None,
) -> str:
    if not api_key:
        label = PROVIDER_LABELS.get(provider, provider)
        raise AssistantError(f"A chave da API do {label} ainda não está configurada.")
    if provider == "groq":
        return _send_groq(api_key, model, system_prompt, history, tools, execute_tool)
    raise AssistantError("Assistente desconhecido.")


def _post_groq(api_key: str, model: str, messages: list[dict[str, Any]], tools) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": MAX_REPLY_TOKENS,
        "temperature": 0.4,
    }
    if tools:
        payload["tools"] = tools
    try:
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as error:
        raise AssistantError("Não foi possível contactar o Groq. Tentem novamente.") from error
    if response.status_code >= 400:
        raise AssistantError("O Groq não conseguiu responder. Tentem novamente em instantes.")
    try:
        return response.json()["choices"][0]["message"]
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise AssistantError("Resposta inesperada do Groq.") from error


def _send_groq(
    api_key: str,
    model: str,
    system_prompt: str,
    history: list[dict[str, str]],
    tools: list[dict[str, Any]] | None,
    execute_tool: ToolExecutor | None,
) -> str:
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}, *history]

    for _ in range(MAX_TOOL_ROUNDS):
        message = _post_groq(api_key, model, messages, tools if execute_tool else None)
        tool_calls = message.get("tool_calls")
        if not tool_calls or not execute_tool:
            return (message.get("content") or "").strip()

        messages.append(message)
        for call in tool_calls:
            function = call.get("function", {})
            name = function.get("name", "")
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except (TypeError, ValueError):
                arguments = {}
            result = execute_tool(name, arguments)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    raise AssistantError("O assistente não conseguiu concluir o pedido a tempo. Tentem de novo.")
