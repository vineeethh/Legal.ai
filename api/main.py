"""FastAPI app for the local Legal.ai web UI.

Run (inside the app container): uvicorn api.main:app --host 0.0.0.0 --port 8000
The compose `api` service binds it to 127.0.0.1:8000 on the host; the Next.js
dev server (service `web`, port 3000) talks to it from the browser.

Single-user local tool: no auth by design. Anything that must never leak
(the OpenRouter key) is only ever accepted, never echoed back.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from dotenv import set_key
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from pipeline.config import OPENROUTER_BASE_URL, get_settings, reset_settings

from . import db
from .jobs import TERMINAL_STATUSES, job_manager

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
JUDGMENTS_DIR = REPO_ROOT / "data" / "judgments"
ENV_PATH = REPO_ROOT / ".env"

MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # hard cap; the pipeline's own guardrail is stricter


@asynccontextmanager
async def lifespan(app: FastAPI):
    job_manager.bind_loop(asyncio.get_running_loop())
    JUDGMENTS_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Legal.ai", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Documents
# --------------------------------------------------------------------------- #


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


def _has_pdf(document_id: str) -> bool:
    return (JUDGMENTS_DIR / f"{document_id}.pdf").exists() or (JUDGMENTS_DIR / f"{document_id}.PDF").exists()


@app.get("/api/documents")
def list_documents() -> list[dict]:
    """Persisted documents (Postgres) merged with in-flight jobs (memory).
    A job that has persisted appears once, with live status from memory."""
    try:
        rows = db.list_documents()
    except Exception:  # DB down shouldn't blank the whole dashboard
        logger.exception("list_documents: DB query failed")
        rows = []
    by_id = {r["id"]: r for r in rows}
    for job in job_manager.all():
        merged = by_id.get(job.document_id, {})
        by_id[job.document_id] = {**merged, **job.summary()}
    docs = list(by_id.values())
    for d in docs:
        d["has_pdf"] = _has_pdf(d["id"])
    docs.sort(key=lambda d: d.get("created_at") or d.get("uploaded_at") or "", reverse=True)
    return docs


@app.post("/api/documents", status_code=201)
async def upload_document(file: UploadFile) -> dict:
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted.")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File exceeds the 100 MB upload cap.")
    if not content.startswith(b"%PDF"):
        raise HTTPException(400, "File does not look like a PDF (missing %PDF header).")

    document_id = str(uuid.uuid4())
    # Stored under the document id (not the user filename) — path-safe, and it
    # makes GET /pdf derivable from the id alone.
    pdf_path = JUDGMENTS_DIR / f"{document_id}.pdf"
    pdf_path.write_bytes(content)

    job = job_manager.submit(document_id, file.filename or "judgment.pdf", str(pdf_path))
    return job.summary()


@app.get("/api/documents/{document_id}")
def get_document(document_id: str) -> dict:
    job = job_manager.get(document_id)
    row = None
    try:
        row = db.get_document(document_id)
    except Exception:
        logger.exception("get_document: DB query failed")
    if job is None and row is None:
        raise HTTPException(404, "Unknown document.")
    merged = {**(row or {}), **(job.summary() if job else {})}
    merged["has_pdf"] = _has_pdf(document_id)
    if job and job.status == "awaiting_review":
        merged["review_payload"] = job.review_payload
    return merged


@app.get("/api/documents/{document_id}/result")
def get_result(document_id: str) -> dict:
    job = job_manager.get(document_id)
    if job is not None and job.result_json is not None:
        return job.result_json
    result = None
    try:
        result = db.get_result(document_id)
    except Exception:
        logger.exception("get_result: DB query failed")
    if result is None:
        raise HTTPException(404, "No persisted result for this document.")
    return result


@app.get("/api/documents/{document_id}/validation")
def get_validation(document_id: str) -> list[dict]:
    try:
        return db.get_validation_logs(document_id)
    except Exception:
        logger.exception("get_validation: DB query failed")
        return []


@app.api_route("/api/documents/{document_id}/pdf", methods=["GET", "HEAD"])
def get_pdf(document_id: str) -> FileResponse:
    # HEAD is allowed so the viewer can probe availability without triggering
    # a pdf.js load error (FastAPI does not add HEAD to GET routes by itself).
    # Web uploads are stored as {document_id}.pdf; also accept .PDF for safety.
    for candidate in (JUDGMENTS_DIR / f"{document_id}.pdf", JUDGMENTS_DIR / f"{document_id}.PDF"):
        if candidate.exists():
            return FileResponse(candidate, media_type="application/pdf")
    raise HTTPException(404, "PDF not available (CLI-era documents keep their original filename).")


# --------------------------------------------------------------------------- #
# Live events (SSE) + human review
# --------------------------------------------------------------------------- #


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.get("/api/documents/{document_id}/events")
async def document_events(document_id: str) -> StreamingResponse:
    job = job_manager.get(document_id)
    if job is None:
        raise HTTPException(404, "No live job for this document (it may predate this server).")

    history, queue = job_manager.subscribe(document_id)

    async def generate():
        try:
            for event in history:
                yield _sse(event)
            if job.status in TERMINAL_STATUSES:
                return
            while True:
                event = await queue.get()
                yield _sse(event)
                if event.get("type") == "status" and event.get("status") in TERMINAL_STATUSES:
                    return
        finally:
            job_manager.unsubscribe(document_id, queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ReviewDecisionIn(BaseModel):
    action: str = Field(..., pattern="^(approve|reject|edit)$")
    patches: dict | None = None


@app.post("/api/documents/{document_id}/review")
def submit_review(document_id: str, decision: ReviewDecisionIn) -> dict:
    payload: dict = {"action": decision.action}
    if decision.action == "edit":
        payload["patches"] = decision.patches or {}
    if not job_manager.submit_review(document_id, payload):
        raise HTTPException(409, "This document is not awaiting review.")
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Settings (bring-your-own-key)
# --------------------------------------------------------------------------- #

# .env keys the UI may write. The API key is write-only: accepted here, masked
# on read, never logged. LLM_API_KEY is generic — it's whatever key the
# configured LLM_BASE_URL needs (OpenRouter, Gemini's OpenAI-compat endpoint,
# Together, Groq, a self-hosted vLLM behind auth, ...).
_SETTINGS_ENV_KEYS = {
    "llm_model": "LLM_MODEL",
    "validator_llm_model": "VALIDATOR_LLM_MODEL",
    "llm_base_url": "LLM_BASE_URL",
    "llm_api_key": "LLM_API_KEY",
    "pipeline_max_concurrency": "PIPELINE_MAX_CONCURRENCY",
    "llm_max_retries": "LLM_MAX_RETRIES",
}


class SettingsIn(BaseModel):
    llm_model: str | None = None
    validator_llm_model: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    pipeline_max_concurrency: int | None = None
    llm_max_retries: int | None = None


@app.get("/api/settings")
def get_settings_view() -> dict:
    s = get_settings()
    key = s.llm_api_key
    return {
        "llm_model": s.llm_model,
        "validator_llm_model": s.validator_llm_model,
        "llm_base_url": s.llm_base_url,
        "is_openrouter": "openrouter.ai" in s.llm_base_url,
        "has_api_key": bool(key),
        "api_key_hint": f"…{key[-4:]}" if key else None,
        "pipeline_max_concurrency": s.pipeline_max_concurrency,
        "llm_max_retries": s.llm_max_retries,
        "confidence_autosave_threshold": s.confidence_autosave_threshold,
        "confidence_review_threshold": s.confidence_review_threshold,
        "max_retries": s.max_retries,
    }


@app.post("/api/settings")
def update_settings(settings_in: SettingsIn) -> dict:
    # Persists to .env AND patches the live process's environment, so the
    # change applies immediately with no restart. Important operational note:
    # `docker compose restart api` reuses the container's environment
    # snapshot from when it was last created — it does NOT re-read .env — so
    # a plain restart after a settings-page change silently reverts to
    # whatever was in .env at creation time. Use `docker compose up -d api`
    # (or `--force-recreate`) to actually pick up .env changes from disk.
    updates = {k: v for k, v in settings_in.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No settings provided.")
    ENV_PATH.touch(exist_ok=True)
    for field_name, value in updates.items():
        env_key = _SETTINGS_ENV_KEYS[field_name]
        set_key(str(ENV_PATH), env_key, str(value), quote_mode="never")
        os.environ[env_key] = str(value)
    reset_settings()
    logger.info("Settings updated: %s", [k for k in updates if k != "llm_api_key"])
    return get_settings_view()


@app.post("/api/settings/test")
async def test_connection() -> dict:
    """Checks the endpoint is reachable, the model is listed, AND that the
    model actually accepts a tool call — every extraction agent depends on
    function-calling for structured output, so 'the endpoint responds' isn't
    enough to know the pipeline will actually work. This spends one small
    completion request (a few tokens) — worth it to catch 'function calling
    not enabled for this model' here rather than after a full, multi-minute
    pipeline run silently produces an empty record."""
    s = get_settings()
    headers = {"Content-Type": "application/json"}
    if s.llm_api_key:
        headers["Authorization"] = f"Bearer {s.llm_api_key}"

    models_url = s.llm_base_url.rstrip("/") + "/models"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(models_url, headers=headers)
    except httpx.HTTPError as exc:
        return {"ok": False, "detail": f"Endpoint unreachable: {type(exc).__name__}"}
    if response.status_code != 200:
        return {"ok": False, "detail": f"Endpoint returned HTTP {response.status_code}."}
    model_found = None
    try:
        ids = {m.get("id") for m in response.json().get("data", [])}
        model_found = s.llm_model in ids if ids else None
    except Exception:
        pass

    chat_url = s.llm_base_url.rstrip("/") + "/chat/completions"
    tool_call_payload = {
        "model": s.llm_model,
        "messages": [{"role": "user", "content": "reply"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "ack",
                    "description": "Acknowledge the request.",
                    "parameters": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
                },
            }
        ],
        "tool_choice": {"type": "function", "function": {"name": "ack"}},
        "max_tokens": 20,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            chat_response = await client.post(chat_url, headers=headers, json=tool_call_payload)
    except httpx.HTTPError as exc:
        return {"ok": False, "model_found": model_found, "detail": f"Tool-call test failed: {type(exc).__name__}"}

    if chat_response.status_code != 200:
        try:
            msg = chat_response.json().get("error", {}).get("message", chat_response.text[:200])
        except Exception:
            msg = chat_response.text[:200]
        return {
            "ok": False,
            "model_found": model_found,
            "detail": f"Model '{s.llm_model}' rejected a tool call (HTTP {chat_response.status_code}): {msg}",
        }

    try:
        tool_calls = chat_response.json()["choices"][0]["message"].get("tool_calls")
    except Exception:
        tool_calls = None
    if not tool_calls:
        return {
            "ok": False,
            "model_found": model_found,
            "detail": (
                f"Model '{s.llm_model}' did not return a tool call — it likely doesn't support "
                "function calling, which every extraction agent in this pipeline requires. "
                "Pick a different model."
            ),
        }

    detail = f"Endpoint reachable — '{s.llm_model}' supports tool calling."
    if model_found is False:
        detail += " (not listed in /models, but the tool-call test succeeded, so this is likely fine.)"
    return {"ok": True, "model_found": model_found, "detail": detail}


# --------------------------------------------------------------------------- #
# Statute KB
# --------------------------------------------------------------------------- #


@app.get("/api/kb/search")
def search_kb(q: str, act: str | None = None) -> list[dict]:
    q = q.strip()
    if len(q) < 2:
        return []
    try:
        return db.kb_search(q, act_version=act)
    except Exception:
        logger.exception("kb_search failed")
        return []


@app.get("/api/kb/stats")
def get_kb_stats() -> dict:
    try:
        return db.kb_stats()
    except Exception:
        logger.exception("kb_stats: DB query failed")
        return {"acts": [], "total_sections": 0, "crosswalk_mappings": 0, "total_runs": 0}


@app.get("/api/models")
async def list_models() -> list[dict]:
    """Free-to-call model catalog from the configured endpoint, trimmed to what
    the settings screen needs (id, name, tool support, pricing)."""
    s = get_settings()
    headers = {}
    if s.llm_api_key:
        headers["Authorization"] = f"Bearer {s.llm_api_key}"
    url = s.llm_base_url.rstrip("/") + "/models"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json().get("data", [])
    except Exception:
        logger.exception("list_models failed")
        return []
    models = []
    for m in data:
        supported = m.get("supported_parameters") or []
        pricing = m.get("pricing") or {}
        models.append(
            {
                "id": m.get("id"),
                "name": m.get("name") or m.get("id"),
                "tools": ("tools" in supported) if supported else None,
                "free": pricing.get("prompt") in ("0", 0, None) and pricing.get("completion") in ("0", 0, None),
                "context_length": m.get("context_length"),
            }
        )
    return models
