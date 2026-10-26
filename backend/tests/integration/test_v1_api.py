from datetime import datetime, timezone

from fastapi.testclient import TestClient
from pymongo import MongoClient

from app.config import settings
from app.main import app
from tests.fixtures import job_payload


def test_ready_checks_mongodb_and_redis(client):
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"mongodb": "ok", "redis": "ok"}


def test_health_is_process_liveness_only(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_correlation_id_is_echoed(client):
    response = client.get("/api/v1/health", headers={"X-Correlation-ID": "phase1-test"})
    assert response.headers["x-correlation-id"] == "phase1-test"


def test_validation_error_uses_the_envelope_and_hides_input(client):
    response = client.post("/api/v1/jobs/import", json={"source": "manual", "description": "secret-note"})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert "secret-note" not in response.text
    assert body["correlation_id"]


def test_v1_import_is_visible_on_the_legacy_list(client):
    created = client.post("/api/v1/jobs/import", json=job_payload("v1-shared")).json()
    assert created["created"] is True
    assert created["source_job_id"] == "v1-shared"

    again = client.post("/api/v1/jobs/import", json=job_payload("v1-shared"))
    assert again.status_code == 200
    assert again.json()["id"] == created["id"]
    assert again.json()["created"] is False

    legacy = client.get("/api/jobs").json()
    assert created["id"] in [job["id"] for job in legacy]
    listed = client.get("/api/v1/jobs").json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == created["id"]


def test_prepare_application_is_dry_run_and_duplicate_is_rejected(client):
    job = client.post("/api/v1/jobs/import", json=job_payload("v1-app")).json()
    created = client.post(f"/api/v1/jobs/{job['id']}/prepare-application", json={})
    assert created.status_code == 201
    body = created.json()
    assert body["dry_run"] is True
    assert body["status"] == "dry_run"

    duplicate = client.post(f"/api/v1/jobs/{job['id']}/prepare-application", json={})
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "duplicate"
    assert duplicate.json()["details"]["application_id"] == body["id"]

    fetched = client.get(f"/api/v1/applications/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["job_id"] == job["id"]
    legacy = client.get("/api/applications").json()
    assert body["id"] in [item["id"] for item in legacy]


def test_unknown_source_and_job_use_safe_errors(client):
    missing = client.get("/api/v1/sources/not-a-source")
    assert missing.status_code == 404
    assert missing.json()["code"] == "unknown_source"
    job = client.get("/api/v1/jobs/not-an-id")
    assert job.status_code == 404
    assert job.json()["code"] == "not_found"


def test_sources_remain_unconfigured(client):
    sources = client.get("/api/v1/sources").json()
    assert {item["source"] for item in sources} >= {"linkedin", "naukri", "wellfound", "career_page", "gmail"}
    assert not any(item["configured"] or item["application_supported"] for item in sources)


def test_settings_persist_across_a_new_process_client(client):
    payload = {
        "dry_run": True,
        "minimum_match_score": 80,
        "search_interval_minutes": 120,
        "followup_enabled": False,
        "global_pause": True,
        "automation_enabled": False,
    }
    saved = client.put("/api/v1/automation/settings", json=payload)
    assert saved.status_code == 200
    assert saved.json()["minimum_match_score"] == 80

    with TestClient(app) as restarted:
        loaded = restarted.get("/api/v1/automation/settings").json()
    assert loaded["minimum_match_score"] == 80
    assert loaded["search_interval_minutes"] == 120
    assert loaded["followup_enabled"] is False
    assert loaded["dry_run"] is True

    job = client.post("/api/jobs/import", json=job_payload("threshold")).json()
    rejected = client.post("/api/applications", json={"job_id": job["id"]})
    assert rejected.status_code == 422


def test_live_mode_stays_rejected_on_v1(client):
    response = client.put(
        "/api/v1/automation/settings",
        json={"dry_run": False, "minimum_match_score": 50, "search_interval_minutes": 60},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "policy_violation"
    assert client.get("/api/v1/automation/settings").json()["dry_run"] is True


def test_previously_stored_job_document_remains_readable(client):
    now = datetime.now(timezone.utc)
    MongoClient(settings.mongodb_url)[settings.mongodb_database].jobs.insert_one(
        {
            "source": "manual",
            "source_job_id": "already-stored",
            "company": "Example Co",
            "title": "Backend Engineer",
            "location": "Remote",
            "description": "Python FastAPI MongoDB Redis REST API",
            "canonical_url": "https://jobs.example.com/already-stored",
            "match_score": 71.5,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
    )
    listed = client.get("/api/v1/jobs").json()
    match = next(item for item in listed["items"] if item["source_job_id"] == "already-stored")
    assert match["match_score"] == 71.5
    assert match["company"] == "Example Co"
