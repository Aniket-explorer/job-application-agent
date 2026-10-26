import json
from datetime import datetime, timezone

from pymongo import MongoClient

from app.core.config import settings
from tests.fixtures import job_payload


def test_score_persists_one_row_and_leaves_the_job_and_application_unchanged(client, tmp_path, monkeypatch):
    profile = tmp_path / "profile.json"
    profile.write_text(
        json.dumps(
            {
                "candidate_id": "default-candidate",
                "skills": [{"name": "Python"}],
                "preferred_roles": ["Backend Engineer"],
                "name": "Should Not Leak",
                "email": "person@example.com",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "profile_path", str(profile))
    monkeypatch.setattr(settings, "resume_storage_path", str(tmp_path / "resumes"))
    created = client.post(
        "/api/v1/jobs/import",
        json=job_payload("score-me", description="Requirements: Python and Kubernetes.\nBackend Engineer"),
    ).json()
    original_score = created["match_score"]
    prepared = client.post(f"/api/v1/jobs/{created['id']}/prepare-application", json={}).json()
    before = _application(prepared["id"])

    first = client.post(f"/api/v1/jobs/{created['id']}/score")
    second = client.post(f"/api/v1/jobs/{created['id']}/score")
    assert first.status_code == 200
    assert second.status_code == 200
    body = first.json()
    assert body["match_status"] == "scored"
    assert body["threshold"] == 50
    assert "Should Not Leak" not in first.text
    assert "person@example.com" not in first.text
    assert body["matched_skills"] == ["python"]
    assert body["missing_skills"] == ["kubernetes"]
    assert MongoClient(settings.mongodb_url)[settings.mongodb_database].job_matches.count_documents({"job_id": created["id"]}) == 1

    listed = client.get("/api/v1/jobs").json()["items"]
    stored = next(item for item in listed if item["id"] == created["id"])
    assert stored["match_score"] == original_score
    assert stored["origin"] == "manual"
    assert stored["assessment"]["total_score"] == body["total_score"]
    assert _application(prepared["id"]) == before


def test_missing_profile_and_invalid_inputs(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "profile_path", str(tmp_path / "missing.json"))
    created = client.post("/api/v1/jobs/import", json=job_payload("no-profile")).json()
    scored = client.post(f"/api/v1/jobs/{created['id']}/score")
    assert scored.status_code == 200
    assert scored.json()["match_status"] == "insufficient_profile"
    assert scored.json()["total_score"] is None
    assert scored.json()["meets_threshold"] is False

    missing = client.post("/api/v1/jobs/not-an-id/score")
    assert missing.status_code == 404
    assert missing.json()["code"] == "not_found"

    invalid = tmp_path / "profile.json"
    invalid.write_text("{", encoding="utf-8")
    monkeypatch.setattr(settings, "profile_path", str(invalid))
    rejected = client.post(f"/api/v1/jobs/{created['id']}/score")
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "profile_invalid"
    assert "Should Not Leak" not in rejected.text


def test_min_score_uses_the_explainable_score(client):
    database = MongoClient(settings.mongodb_url)[settings.mongodb_database]
    unscored = _insert_job(database, "import-only", 95)
    boundary = _insert_job(database, "boundary", 10)
    below = _insert_job(database, "below", 99)
    empty = _insert_job(database, "null-score", 90)
    _insert_match(database, boundary, 50.0)
    _insert_match(database, below, 49.9)
    _insert_match(database, empty, None)

    at_threshold = _ids(client.get("/api/v1/jobs?min_score=50"))
    above_boundary = _ids(client.get("/api/v1/jobs?min_score=50.1"))
    unfiltered = _ids(client.get("/api/v1/jobs?min_score=0"))
    assert at_threshold == {boundary}
    assert boundary not in above_boundary
    assert below not in at_threshold
    assert empty not in at_threshold
    assert unscored not in at_threshold
    assert {unscored, boundary, below, empty} <= unfiltered

    listed = client.get("/api/v1/jobs?min_score=0").json()["items"]
    manual = next(item for item in listed if item["id"] == unscored)
    assert manual["origin"] == "manual"
    assert manual["match_score"] == 95
    assert "assessment" not in manual


def test_profile_status_reports_a_missing_file_without_creating_one(client, tmp_path, monkeypatch):
    missing = tmp_path / "profile.json"
    monkeypatch.setattr(settings, "profile_path", str(missing))
    response = client.get("/api/v1/profile/status")
    assert response.status_code == 200
    body = response.json()
    assert body["profile_present"] is False
    assert body["warnings"] == ["profile_missing"]
    assert "email" not in body
    assert missing.exists() is False


def test_origin_filter_keeps_manual_records_separate(client):
    now = datetime.now(timezone.utc)
    database = MongoClient(settings.mongodb_url)[settings.mongodb_database]
    database.jobs.insert_one(
        {
            "source": "career_page",
            "source_job_id": "greenhouse:exampleboard:1",
            "origin": "discovered",
            "company": "Example Company",
            "title": "Platform Engineer",
            "description": "Python",
            "canonical_url": "https://jobs.example.com/discovered-1",
            "match_score": 80,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
    )
    client.post("/api/v1/jobs/import", json=job_payload("manual-only"))
    manual = client.get("/api/v1/jobs?origin=manual").json()
    discovered = client.get("/api/v1/jobs?origin=discovered").json()
    assert manual["total"] == 1
    assert manual["items"][0]["origin"] == "manual"
    assert discovered["total"] == 1
    assert discovered["items"][0]["origin"] == "discovered"
    invalid = client.get("/api/v1/jobs?origin=other")
    assert invalid.status_code == 422


def _insert_job(database, source_job_id: str, match_score: float) -> str:
    now = datetime.now(timezone.utc)
    inserted = database.jobs.insert_one(
        {
            "source": "manual",
            "source_job_id": source_job_id,
            "company": "Example Co",
            "title": "Backend Engineer",
            "description": "Stored for the score filter.",
            "canonical_url": f"https://jobs.example.com/{source_job_id}",
            "match_score": match_score,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
    )
    return str(inserted.inserted_id)


def _insert_match(database, job_id: str, total_score: float | None) -> None:
    database.job_matches.insert_one(
        {
            "candidate_id": "default-candidate",
            "job_id": job_id,
            "matching_version": "phase2-v1",
            "total_score": total_score,
            "match_status": "scored" if total_score is not None else "insufficient_information",
            "factors": [],
            "matched_skills": [],
            "missing_skills": [],
            "warnings": [],
        }
    )


def _ids(response) -> set[str]:
    assert response.status_code == 200
    return {item["id"] for item in response.json()["items"]}


def _application(application_id: str) -> dict:
    document = MongoClient(settings.mongodb_url)[settings.mongodb_database].applications.find_one({"_id": __import__("bson").ObjectId(application_id)})
    document.pop("_id")
    return document
