"""API settings — read from the environment once, like pipeline/config.py.

Kept separate from pipeline.config.Settings on purpose: that class *requires*
OPENROUTER_API_KEY / DATABASE_URL / QDRANT_URL, and the API has to start
without them in demo mode.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _get_bool(name: str, default: bool) -> bool:
    raw = _get(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _get_float(name: str, default: float) -> float:
    raw = _get(name)
    return float(raw) if raw else default


def _get_int(name: str, default: int) -> int:
    raw = _get(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class ApiSettings:
    # Demo mode swaps the real pipeline for a scripted one (api/demo.py) so the
    # API and UI can run on a machine without Docling/torch/LLM credentials.
    demo_mode: bool = field(default_factory=lambda: _get_bool("LEGAL_AI_DEMO_MODE", False))
    # Empty = no auth. When set, every /api route except /api/health needs a
    # matching `X-API-Key` header.
    api_key: str = field(default_factory=lambda: _get("API_KEY"))

    upload_dir: Path = field(default_factory=lambda: Path(_get("API_UPLOAD_DIR") or REPO_ROOT / "data" / "uploads"))
    jobs_dir: Path = field(default_factory=lambda: Path(_get("API_JOBS_DIR") or REPO_ROOT / "data" / "api_jobs"))
    eval_reports_dir: Path = field(
        default_factory=lambda: Path(_get("API_EVAL_REPORTS_DIR") or REPO_ROOT / "evaluation" / "reports")
    )
    ui_dist_dir: Path = field(default_factory=lambda: REPO_ROOT / "ui" / "dist")

    max_upload_mb: float = field(
        default_factory=lambda: _get_float("API_MAX_UPLOAD_MB", _get_float("PDF_MAX_SIZE_MB", 50.0))
    )
    # Documents processed at the same time. 1 by default: the embedding and
    # Docling models are process-wide singletons that are not built for
    # concurrent first use, and each run already parallelises its 6 agents.
    max_concurrent_jobs: int = field(default_factory=lambda: _get_int("API_MAX_CONCURRENT_JOBS", 1))
    # Write finished runs to Postgres via pipeline.persistence.save_run (real mode only).
    save_to_db: bool = field(default_factory=lambda: _get_bool("API_SAVE_TO_DB", True))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip() for o in _get("API_CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()
        )
    )
    # Seconds between simulated graph steps in demo mode.
    demo_step_seconds: float = field(default_factory=lambda: _get_float("DEMO_STEP_SECONDS", 0.6))

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)
