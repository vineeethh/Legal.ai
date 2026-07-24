"""LLM access — any OpenAI-compatible endpoint (OpenRouter by default, or a
local server: Ollama, vLLM, LM Studio) via `LLM_BASE_URL`.

Two entry points, matching the two ways the pipeline calls an LLM:
  - `get_chat_model()` — a LangChain `ChatOpenAI` pointed at the configured
    endpoint, for use inside LangGraph nodes (traced automatically via the
    LangGraph CallbackHandler, see observability/langfuse_client.py).
  - `get_traced_client()` — the raw OpenAI-compatible client, Langfuse-wrapped,
    for any agent that calls the LLM directly outside a LangChain node
    (OpenRouter-specific — direct calls elsewhere aren't traced this way).

Structured output (Pydantic models) goes through `get_chat_model(...).with_structured_output(Schema)`.
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from .config import get_settings

# Hostnames that mean "this endpoint runs on this machine/network, no auth
# needed" — Ollama, vLLM, LM Studio, etc. Anything else (OpenRouter, Gemini's
# OpenAI-compat endpoint, Together, Groq, a hosted vLLM behind auth, ...) is
# treated as a cloud endpoint that requires a real key.
_LOCAL_HOSTS = ("localhost", "127.0.0.1", "host.docker.internal", "0.0.0.0")


def _is_local_endpoint(base_url: str) -> bool:
    return any(host in base_url for host in _LOCAL_HOSTS)


def _resolve_api_key(settings) -> str:
    """A cloud endpoint needs a real key; a local OpenAI-compatible endpoint
    accepts any placeholder. Validated here at call time rather than at
    startup so the free/local path works with no key configured."""
    if settings.llm_api_key:
        return settings.llm_api_key
    if _is_local_endpoint(settings.llm_base_url):
        return "not-needed"
    raise RuntimeError(
        f"No API key configured for LLM_BASE_URL={settings.llm_base_url!r}. Set "
        "LLM_API_KEY in .env (or the Settings page) for this endpoint — e.g. an "
        "OpenRouter key, a Gemini key (https://generativelanguage.googleapis.com/"
        "v1beta/openai/), or any other OpenAI-compatible provider's key. Or point "
        "LLM_BASE_URL at a local endpoint (e.g. Ollama: "
        "http://host.docker.internal:11434/v1), which needs no key."
    )


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
        api_key=_resolve_api_key(settings),
        base_url=settings.llm_base_url,
        # Exponential backoff on 429/5xx (honors Retry-After) so a transient
        # rate-limit doesn't abort a whole document run.
        max_retries=settings.llm_max_retries,
    )


def get_traced_client():
    """Langfuse-instrumented OpenAI-compatible client, pointed at OpenRouter."""
    from observability import get_openrouter_client

    return get_openrouter_client()
