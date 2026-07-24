"""Central config — every module reads settings from here, never os.environ directly.

Keeps env parsing, defaults, and validation in one place so a missing/malformed
var fails at startup with a clear message instead of deep inside a pipeline run.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else default


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def _with_keepalives(url: str) -> str:
    """Append TCP keepalive params so long pipeline runs survive pooler/NAT
    idle drops. Supabase's pooler closes quiet connections, and a Docling parse
    or a slow agent leaves the LangGraph checkpointer connection silent for
    minutes — the next write then fails with 'SSL error: unexpected eof while
    reading'. Keepalives every 30s keep the path alive end to end."""
    if not url or not url.startswith(("postgres://", "postgresql://")) or "keepalives" in url:
        return url
    sep = "&" if "?" in url else "?"
    return url + sep + "keepalives=1&keepalives_idle=30&keepalives_interval=10&keepalives_count=5&connect_timeout=15"


DEFAULT_LLM_MODEL = "openai/gpt-4o-mini"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _resolve_llm_api_key() -> str:
    explicit = _get("LLM_API_KEY")
    if explicit:
        return explicit
    # OPENROUTER_API_KEY is a legacy fallback for .env files predating the
    # generic name — but only when the endpoint actually IS OpenRouter.
    # Falling back unconditionally would silently send an OpenRouter key to
    # whatever other provider LLM_BASE_URL now points at (Gemini, Together,
    # ...), which is wrong, not just unnecessary.
    base_url = _get("LLM_BASE_URL", OPENROUTER_BASE_URL)
    if "openrouter.ai" in base_url:
        return _get("OPENROUTER_API_KEY")
    return ""


@dataclass(frozen=True)
class Settings:
    # LLM provider — OpenRouter by default, but any OpenAI-compatible endpoint
    # works (e.g. Ollama at http://host.docker.internal:11434/v1, or vLLM).
    # The API key is validated at call time in pipeline/llm.py rather than
    # required at startup: local endpoints like Ollama don't need one, so a
    # hard _require() here would wrongly block the free/local path.
    llm_base_url: str = field(default_factory=lambda: _get("LLM_BASE_URL", OPENROUTER_BASE_URL))
    # Generic key for whatever LLM_BASE_URL points at (OpenRouter, Gemini's
    # OpenAI-compat endpoint, Together, Groq, a self-hosted vLLM behind auth,
    # ...). See _resolve_llm_api_key for the OPENROUTER_API_KEY legacy fallback.
    llm_api_key: str = field(default_factory=_resolve_llm_api_key)
    llm_model: str = field(default_factory=lambda: _get("LLM_MODEL") or DEFAULT_LLM_MODEL)
    validator_llm_model: str = field(
        default_factory=lambda: _get("VALIDATOR_LLM_MODEL") or _get("LLM_MODEL") or DEFAULT_LLM_MODEL
    )

    # Embeddings
    embedding_model: str = field(default_factory=lambda: _get("EMBEDDING_MODEL", "BAAI/bge-m3"))
    reranker_model: str = field(default_factory=lambda: _get("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3"))

    # Qdrant (statute KB)
    qdrant_url: str = field(default_factory=lambda: _require("QDRANT_URL"))
    qdrant_api_key: str = field(default_factory=lambda: _get("QDRANT_API_KEY"))
    qdrant_collection: str = field(default_factory=lambda: _get("QDRANT_COLLECTION", "statutes"))

    # Postgres / Supabase — keepalives appended so every consumer (checkpointer,
    # persistence, verification, web API) gets a drop-resistant connection.
    database_url: str = field(default_factory=lambda: _with_keepalives(_require("DATABASE_URL")))

    # Langfuse
    langfuse_public_key: str = field(default_factory=lambda: _get("LANGFUSE_PUBLIC_KEY"))
    langfuse_secret_key: str = field(default_factory=lambda: _get("LANGFUSE_SECRET_KEY"))
    langfuse_base_url: str = field(default_factory=lambda: _get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"))

    # Docling / OCR
    docling_ocr_density_threshold: float = field(
        default_factory=lambda: _get_float("DOCLING_OCR_DENSITY_THRESHOLD", 0.1)
    )

    # Pipeline thresholds
    confidence_autosave_threshold: float = field(
        default_factory=lambda: _get_float("CONFIDENCE_AUTOSAVE_THRESHOLD", 0.90)
    )
    confidence_review_threshold: float = field(
        default_factory=lambda: _get_float("CONFIDENCE_REVIEW_THRESHOLD", 0.80)
    )
    max_retries: int = field(default_factory=lambda: _get_int("MAX_RETRIES", 3))
    retry_temperatures: tuple[float, ...] = (0.0, 0.4, 0.7)

    # LLM client resilience + pipeline concurrency.
    # llm_max_retries: OpenAI-client retries (exponential backoff, honors
    #   Retry-After) so a transient 429 doesn't abort a run.
    # pipeline_max_concurrency: cap on concurrent LangGraph nodes. 0 = unlimited
    #   (full agent fan-out). Set to 1 on rate-limited/free LLM tiers to
    #   serialize the fan-out so 6 agents don't fire simultaneously.
    llm_max_retries: int = field(default_factory=lambda: _get_int("LLM_MAX_RETRIES", 5))
    pipeline_max_concurrency: int = field(default_factory=lambda: _get_int("PIPELINE_MAX_CONCURRENCY", 0))

    # Guardrails
    pdf_max_size_mb: float = field(default_factory=lambda: _get_float("PDF_MAX_SIZE_MB", 50.0))
    pdf_max_pages: int = field(default_factory=lambda: _get_int("PDF_MAX_PAGES", 600))


_settings: Settings | None = None


def get_settings() -> Settings:
    """Process-wide Settings singleton, built lazily so importing this module
    doesn't require env vars to already be set until a caller actually asks
    for them."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Drop the cached singleton so the next get_settings() re-reads the
    environment. Used by the local web API's settings endpoint after it
    updates .env/os.environ (model switch, key change) at runtime."""
    global _settings
    _settings = None
