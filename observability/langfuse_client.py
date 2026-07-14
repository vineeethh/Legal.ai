"""Langfuse client setup (SDK v3).

Reads LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_BASE_URL from the
environment (see .env.example). All tracing in the pipeline should go through
these helpers rather than constructing Langfuse/CallbackHandler instances
ad hoc, so trace attributes (session/user/tags) stay consistent across the
6 extraction agents, the validator, and the LangGraph supervisor.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from langfuse import get_client
from langfuse.langchain import CallbackHandler

logger = logging.getLogger(__name__)


def langfuse_enabled() -> bool:
    """True only when both Langfuse keys are set. Tracing is optional: with no
    keys the pipeline runs normally, just without traces (see .env.example)."""
    return bool(
        os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
        and os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
    )


def get_langfuse_client():
    """Return the process-wide Langfuse client singleton."""
    return get_client()


def verify_langfuse_connection() -> bool:
    """Auth-check Langfuse credentials; log and return False rather than raise.

    Call this once at pipeline startup so a misconfigured key fails loudly
    before a 200-page document run rather than silently dropping traces.

    Returns False (never raises) when Langfuse is unconfigured or the auth check
    fails, so a missing/bad key disables tracing instead of aborting the run —
    the SDK's auth_check() itself raises on a 401, so it must be guarded here.
    """
    if not langfuse_enabled():
        logger.info("Langfuse: not configured (no keys) — tracing disabled.")
        return False
    try:
        ok = get_langfuse_client().auth_check()
    except Exception as exc:  # SDK raises (e.g. UnauthorizedError) on a bad key
        logger.warning("Langfuse: auth check failed (%s) — tracing will be a no-op", exc)
        return False
    if ok:
        logger.info("Langfuse: authenticated (%s)", os.environ.get("LANGFUSE_BASE_URL", "default host"))
    else:
        logger.warning("Langfuse: auth check failed — tracing will be a no-op")
    return ok


def get_langgraph_handler() -> CallbackHandler:
    """CallbackHandler to pass into LangGraph's `config={"callbacks": [...]}`."""
    return CallbackHandler()


def traced_run_config(
    session_id: str | None = None,
    user_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the LangGraph run `config` dict with Langfuse trace attributes wired in.

    Use one `session_id` per document run so all 6 agents + validator +
    retries land under a single trace in the Langfuse UI.
    """
    lf_metadata: dict[str, Any] = dict(metadata or {})
    if session_id is not None:
        lf_metadata["langfuse_session_id"] = session_id
    if user_id is not None:
        lf_metadata["langfuse_user_id"] = user_id
    if tags is not None:
        lf_metadata["langfuse_tags"] = tags

    # Attach the tracing callback only when Langfuse is configured, so an
    # unconfigured run doesn't construct a handler that fails on flush.
    callbacks = [get_langgraph_handler()] if langfuse_enabled() else []
    return {"callbacks": callbacks, "metadata": lf_metadata}


def get_openrouter_client():
    """OpenAI-compatible client for direct (non-LangChain) OpenRouter calls,
    auto-traced via Langfuse's OpenAI drop-in wrapper.

    Use this for any agent that calls the LLM directly rather than through a
    LangChain/LangGraph node (which is instead traced via the CallbackHandler
    from `get_langgraph_handler`).
    """
    from langfuse.openai import OpenAI

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set — required for direct OpenRouter calls.")
    return OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )
