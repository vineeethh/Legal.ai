"""HTTP API in demo mode: upload -> progress -> review -> result. No Docling/LLM/DB needed."""

from __future__ import annotations

import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from api.config import ApiSettings
from api.main import create_app

PDF_BYTES = b"%PDF-1.4\n% minimal test file\n"


@pytest.fixture
def settings(tmp_path):
    return replace(
        ApiSettings(),
        demo_mode=True,
        api_key="",
        upload_dir=tmp_path / "uploads",
        jobs_dir=tmp_path / "jobs",
        eval_reports_dir=tmp_path / "reports",
        ui_dist_dir=tmp_path / "no-ui",
        demo_step_seconds=0.0,
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def upload(client, name="judgment.pdf", data=PDF_BYTES, headers=None):
    return client.post("/api/documents", files={"file": (name, data, "application/pdf")}, headers=headers or {})


def wait_for(client, job_id, statuses, headers=None, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/documents/{job_id}", headers=headers or {}).json()
        if job["status"] in statuses:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job never reached {statuses}; last status {job['status']}")


def test_health(client):
    assert client.get("/api/health").json() == {
        "status": "ok",
        "mode": "demo",
        "auth_required": False,
        "version": "0.1.0",
    }


def test_upload_to_result(client):
    response = upload(client)
    assert response.status_code == 202
    job_id = response.json()["id"]

    job = wait_for(client, job_id, {"completed"})
    assert job["decision"] == "auto_save"
    assert job["confidence_score"] == pytest.approx(0.915)
    assert all(a["status"] == "done" for a in job["progress"]["agents"].values())
    assert job["progress"]["agents"]["statute"]["attempts"] == 2  # one retry

    result = client.get(f"/api/documents/{job_id}/result").json()
    assert result["metadata"]["court"]["value"] == "High Court of Karnataka at Bengaluru"
    assert client.get(f"/api/documents/{job_id}/pdf").content == PDF_BYTES
    assert [j["id"] for j in client.get("/api/documents").json()] == [job_id]


def test_review_flow(client):
    job_id = upload(client, name="needs_review.pdf").json()["id"]
    wait_for(client, job_id, {"awaiting_review"})

    assert client.get(f"/api/documents/{job_id}/result").status_code == 409
    payload = client.get(f"/api/documents/{job_id}/review").json()
    assert payload["confidence_score"] < 0.8
    assert payload["flagged_fields"]

    assert client.post(f"/api/documents/{job_id}/review", json={"action": "edit", "patches": {"nope": 1}}).status_code == 422
    assert client.post(f"/api/documents/{job_id}/review", json={"action": "edit", "patches": {"metadata": 5}}).status_code == 422

    preview = payload["result_preview"]
    metadata = preview["metadata"]
    metadata["case_number"] = {"value": "Criminal Appeal No. 412 of 2018", "sources": [metadata["court"]["sources"][0]]}
    response = client.post(f"/api/documents/{job_id}/review", json={"action": "edit", "patches": {"metadata": metadata}})
    assert response.status_code == 202

    job = wait_for(client, job_id, {"completed"})
    assert job["review_decision"]["action"] == "edit"
    result = client.get(f"/api/documents/{job_id}/result").json()
    assert result["metadata"]["case_number"]["value"] == "Criminal Appeal No. 412 of 2018"

    # Review is a one-shot: a second decision is refused.
    assert client.post(f"/api/documents/{job_id}/review", json={"action": "approve"}).status_code == 409


def test_unsafe_pdf_is_rejected(client):
    job_id = upload(client, name="unsafe.pdf").json()["id"]
    job = wait_for(client, job_id, {"rejected"})
    assert job["rejection_reasons"]
    assert client.get(f"/api/documents/{job_id}/result").status_code == 409


@pytest.mark.parametrize(("name", "data"), [("notes.txt", PDF_BYTES), ("fake.pdf", b"hello")])
def test_non_pdf_upload_refused(client, name, data):
    assert upload(client, name=name, data=data).status_code == 415


def test_upload_size_limit(settings):
    with TestClient(create_app(replace(settings, max_upload_mb=0.00001))) as c:
        assert upload(c, data=PDF_BYTES + b"x" * 100).status_code == 413


def test_api_key(settings):
    with TestClient(create_app(replace(settings, api_key="secret"))) as c:
        assert c.get("/api/health").status_code == 200  # health stays open
        assert c.get("/api/documents").status_code == 401
        assert c.get("/api/documents", headers={"X-API-Key": "wrong"}).status_code == 401
        assert c.get("/api/documents", headers={"X-API-Key": "secret"}).status_code == 200


def test_finished_jobs_survive_restart_and_running_ones_fail(settings):
    with TestClient(create_app(settings)) as c:
        done_id = upload(c).json()["id"]
        wait_for(c, done_id, {"completed"})
        paused_id = upload(c, name="review_me.pdf").json()["id"]
        wait_for(c, paused_id, {"awaiting_review"})

    with TestClient(create_app(settings)) as c:
        assert c.get(f"/api/documents/{done_id}").json()["status"] == "completed"
        restarted = c.get(f"/api/documents/{paused_id}").json()
        assert restarted["status"] == "failed"
        assert "restarted" in restarted["error"]


def test_eval_reports(settings, client):
    assert client.get("/api/eval/reports/latest").status_code == 404
    settings.eval_reports_dir.mkdir(parents=True)
    (settings.eval_reports_dir / "20260101T000000Z.json").write_text(
        '{"run": {"created_at": "2026-01-01", "documents_scored": 2, "synthetic": true}, "summary": {}}'
    )
    reports = client.get("/api/eval/reports").json()
    assert reports == [{"name": "20260101T000000Z", "created_at": "2026-01-01", "documents": 2, "synthetic": True}]
    assert client.get("/api/eval/reports/latest").json()["run"]["documents_scored"] == 2
    assert client.get("/api/eval/reports/..%2F..%2Fsecrets").status_code == 404
