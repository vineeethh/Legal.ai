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


DEFAULT_LLM_MODEL = "anthropic/claude-sonnet-5"


@dataclass(frozen=True)
class Settings:
    # LLM (OpenRouter)
    openrouter_api_key: str = field(default_factory=lambda: _require("OPENROUTER_API_KEY"))
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

    # Postgres / Supabase
    database_url: str = field(default_factory=lambda: _require("DATABASE_URL"))

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
