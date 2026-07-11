"""LLM access — OpenRouter only, per project decision.

Two entry points, matching the two ways the pipeline calls an LLM:
  - `get_chat_model()` — a LangChain `ChatOpenAI` pointed at OpenRouter, for use
    inside LangGraph nodes (traced automatically via the LangGraph CallbackHandler,
    see observability/langfuse_client.py).
  - `get_traced_client()` — the raw OpenAI-compatible client, Langfuse-wrapped,
    for any agent that calls the LLM directly outside a LangChain node.

Structured output (Pydantic models) goes through `get_chat_model(...).with_structured_output(Schema)`.
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from .config import get_settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def get_chat_model(
    *,
    model: str | None = None,
    temperature: float = 0.0,
    top_p: float | None = None,
    max_tokens: int | None = None,
) -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=model or settings.llm_model,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        api_key=settings.openrouter_api_key,
        base_url=OPENROUTER_BASE_URL,
    )


def get_traced_client():
    """Langfuse-instrumented OpenAI-compatible client, pointed at OpenRouter."""
    from observability import get_openrouter_client

    return get_openrouter_client()
