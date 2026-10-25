"""Runs against a live docker compose stack. Set SMOKE_BASE_URL, e.g. http://localhost:8000."""

import os
import time
import uuid

import httpx
import pytest

from tests.fixtures import job_payload

BASE_URL = os.getenv("SMOKE_BASE_URL")

pytestmark = pytest.mark.skipif(not BASE_URL, reason="SMOKE_BASE_URL not set; smoke tests need a running stack")


@pytest.fixture(scope="module")
def api():
    with httpx.Client(base_url=BASE_URL, timeout=10) as http:
        deadline = time.monotonic() + 90
        while True:
            try:
                if http.get("/health").json().get("mongodb") == "ok":
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                pytest.fail("Stack did not become healthy within 90 seconds")
            time.sleep(2)
        yield http


def test_all_connectors_registered_and_unconfigured(api):
    connectors = api.get("/api/connectors").json()
    assert {c["source"] for c in connectors} >= {"linkedin", "naukri", "wellfound", "career_page", "gmail"}
    assert not any(c["configured"] or c["application_supported"] for c in connectors)


def test_import_evaluate_and_dry_run_application_flow(api):
    job = api.post("/api/jobs/import", json=job_payload(f"smoke-{uuid.uuid4().hex[:8]}")).json()
    assert job["match_score"] >= 50

    application = api.post("/api/applications", json={"job_id": job["id"]}).json()
    assert application["dry_run"] is True
    assert application["status"] == "dry_run"


def test_live_submission_is_blocked(api):
    response = api.put("/api/settings", json={"dry_run": False, "minimum_match_score": 50})
    assert response.status_code == 400
    assert api.get("/api/settings").json()["dry_run"] is True
