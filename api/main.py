"""FastAPI app.

    uvicorn api.main:app --port 8000                        # real pipeline
    LEGAL_AI_DEMO_MODE=1 uvicorn api.main:app --port 8000   # no Docling/LLM needed

Request flow for one document:
    POST /api/documents              -> 202 + job id; the run starts in a background thread
    GET  /api/documents/{id}         -> status + live progress (poll this)
    GET  /api/documents/{id}/review  -> flagged fields, when status == awaiting_review
    POST /api/documents/{id}/review  -> approve | reject | edit; the paused graph resumes
    GET  /api/documents/{id}/result  -> the StructuredJudgment, when status == completed
"""

from __future__ import annotations

import json
import logging
import secrets
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, File, Header, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from schemas import StructuredJudgment

from .config import ApiSettings
from .jobs import Job, JobStatus, JobStore
from .models import EvalReportSummary, HealthOut, JobOut, ReviewIn
from .pipelines import Pipeline, RealPipeline
from .worker import JobRunner

API_VERSION = "0.1.0"
UPLOAD_CHUNK_BYTES = 1024 * 1024

logger = logging.getLogger(__name__)


def _build_pipeline(settings: ApiSettings) -> Pipeline:
    if settings.demo_mode:
        from .demo import DemoPipeline

        return DemoPipeline(step_seconds=settings.demo_step_seconds)
    return RealPipeline(save_to_db=settings.save_to_db)


def create_app(settings: ApiSettings | None = None, pipeline: Pipeline | None = None) -> FastAPI:
    settings = settings or ApiSettings()
    pipeline = pipeline or _build_pipeline(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        pipeline.check_ready()
        store = JobStore(settings.jobs_dir)
        store.load()
        app.state.store = store
        app.state.runner = JobRunner(store, pipeline, max_concurrent_jobs=settings.max_concurrent_jobs)
        logger.info("Legal.ai API started in %s mode", "demo" if settings.demo_mode else "live")
        yield

    app = FastAPI(
        title="Legal.ai API",
        version=API_VERSION,
        description="Upload an Indian court judgment PDF and get back a structured, source-cited record.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
        if settings.api_key and not secrets.compare_digest(x_api_key or "", settings.api_key):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or invalid X-API-Key header.")

    def store_of(request: Request) -> JobStore:
        return request.app.state.store

    def runner_of(request: Request) -> JobRunner:
        return request.app.state.runner

    def get_job_or_404(job_id: str, store: JobStore = Depends(store_of)) -> Job:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"No document with id {job_id}.")
        return job

    @app.get("/api/health", response_model=HealthOut, tags=["meta"])
    def health() -> HealthOut:
        return HealthOut(
            mode="demo" if settings.demo_mode else "live",
            auth_required=bool(settings.api_key),
            version=API_VERSION,
        )

    router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])

    @router.post(
        "/documents",
        response_model=JobOut,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["documents"],
        summary="Upload a judgment PDF and start processing it",
    )
    async def create_document(
        file: UploadFile = File(...),
        store: JobStore = Depends(store_of),
        runner: JobRunner = Depends(runner_of),
    ) -> JobOut:
        filename = Path(file.filename or "upload.pdf").name
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only .pdf files are accepted.")

        job_id = str(uuid.uuid4())
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        dest = settings.upload_dir / f"{job_id}.pdf"
        size = 0
        header = b""
        # Stream to disk with a hard size cap instead of reading the whole upload into memory.
        with dest.open("wb") as out:
            while chunk := await file.read(UPLOAD_CHUNK_BYTES):
                if size == 0:
                    header = chunk[:5]
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        413,
                        f"File exceeds the {settings.max_upload_mb:g} MB limit.",
                    )
                out.write(chunk)
        if header != b"%PDF-":
            dest.unlink(missing_ok=True)
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "File is not a PDF.")

        job = store.add(Job(id=job_id, filename=filename, pdf_path=str(dest), demo=settings.demo_mode))
        runner.submit(job_id)
        return JobOut.from_job(job)

    @router.get("/documents", response_model=list[JobOut], tags=["documents"], summary="List all runs, newest first")
    def list_documents(store: JobStore = Depends(store_of)) -> list[JobOut]:
        return [JobOut.from_job(job) for job in store.list()]

    @router.get("/documents/{job_id}", response_model=JobOut, tags=["documents"], summary="Status and live progress")
    def get_document(job: Job = Depends(get_job_or_404)) -> JobOut:
        return JobOut.from_job(job)

    @router.get("/documents/{job_id}/result", tags=["documents"], summary="The structured judgment (when completed)")
    def get_result(job: Job = Depends(get_job_or_404)) -> dict:
        if job.result is None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"No result yet; status is {job.status.value}.")
        return job.result

    @router.get("/documents/{job_id}/pdf", tags=["documents"], summary="Download the uploaded PDF")
    def get_pdf(job: Job = Depends(get_job_or_404)) -> FileResponse:
        path = Path(job.pdf_path)
        if not path.exists():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "The uploaded file is no longer on disk.")
        return FileResponse(
            path,
            media_type="application/pdf",
            filename=job.filename,
            content_disposition_type="inline",
        )

    @router.get("/documents/{job_id}/review", tags=["review"], summary="What the reviewer needs to decide")
    def get_review(job: Job = Depends(get_job_or_404)) -> dict:
        if job.status != JobStatus.AWAITING_REVIEW or job.review_payload is None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Not awaiting review; status is {job.status.value}.")
        return job.review_payload

    @router.post(
        "/documents/{job_id}/review",
        response_model=JobOut,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["review"],
        summary="Approve, reject or edit a paused run",
    )
    def submit_review(
        body: ReviewIn,
        job: Job = Depends(get_job_or_404),
        store: JobStore = Depends(store_of),
        runner: JobRunner = Depends(runner_of),
    ) -> JobOut:
        if job.status != JobStatus.AWAITING_REVIEW or job.review_payload is None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Not awaiting review; status is {job.status.value}.")

        decision: dict = {"action": body.action}
        if body.action == "edit":
            patches = body.patches or {}
            if not patches:
                raise HTTPException(422, "An edit needs at least one patch.")
            unknown = sorted(set(patches) - set(StructuredJudgment.model_fields))
            if unknown:
                raise HTTPException(
                    422, f"Unknown top-level fields: {', '.join(unknown)}."
                )
            # Validate here so a bad patch is a 422 for the reviewer, not a crashed run.
            try:
                StructuredJudgment.model_validate({**job.review_payload["result_preview"], **patches})
            except ValidationError as exc:
                raise HTTPException(422, json.loads(exc.json())) from exc
            decision["patches"] = patches

        if not runner.submit_review(job.id, decision):
            raise HTTPException(status.HTTP_409_CONFLICT, "This run is no longer waiting for review.")
        return JobOut.from_job(store.get(job.id) or job)

    def _report_paths() -> list[Path]:
        if not settings.eval_reports_dir.exists():
            return []
        return sorted(settings.eval_reports_dir.glob("*.json"), key=lambda p: p.name, reverse=True)

    def _read_report(path: Path) -> dict:
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Unreadable report {path.name}.") from exc

    @router.get("/eval/reports", response_model=list[EvalReportSummary], tags=["evaluation"])
    def list_eval_reports() -> list[EvalReportSummary]:
        summaries = []
        for path in _report_paths():
            report = _read_report(path)
            run = report.get("run", {})
            summaries.append(
                EvalReportSummary(
                    name=path.stem,
                    created_at=run.get("created_at"),
                    documents=run.get("documents_scored"),
                    synthetic=bool(run.get("synthetic")),
                )
            )
        return summaries

    @router.get("/eval/reports/{name}", tags=["evaluation"], summary="One report; name 'latest' for the newest")
    def get_eval_report(name: str) -> dict:
        paths = _report_paths()
        if not paths:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No evaluation reports yet. Run python -m evaluation.run_eval.")
        if name == "latest":
            return _read_report(paths[0])
        # Only names of files actually in the reports dir — no path traversal.
        for path in paths:
            if path.stem == name:
                return _read_report(path)
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No report named {name}.")

    app.include_router(router)

    # Serve the built UI from the same origin when it exists (ui/ -> npm run build).
    if (settings.ui_dist_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=settings.ui_dist_dir, html=True), name="ui")

    return app


app = create_app()
