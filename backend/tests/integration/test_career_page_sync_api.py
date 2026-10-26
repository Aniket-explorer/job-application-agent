import json
from datetime import datetime, timezone

import httpx
import pytest
import redis
from pymongo import MongoClient

from app.connectors.career_page.greenhouse import greenhouse_rate_limit_key, greenhouse_source_job_id
from app.core.config import settings
from app.repositories.jobs import JobRepository
from app.services.discovery import GreenhouseRateLimiter
from tests.fixtures import job_payload

CANARY = "SECRET-RESUME-TEXT-DO-NOT-LEAK"
TOKEN = "fixtureboard"
OTHER = "missingboard"


def test_disabled_and_unconfigured_sync_make_no_request(client, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("external client created")

    monkeypatch.setattr("app.services.discovery.httpx.AsyncClient", explode)
    monkeypatch.setattr(settings, "enable_career_page_connector", False)
    monkeypatch.setattr(settings, "greenhouse_boards", f"{TOKEN}|Fixture Co")
    disabled = client.post("/api/v1/sources/career_page/sync")
    assert disabled.status_code == 422
    assert disabled.json()["code"] == "connector_disabled"
    assert TOKEN not in disabled.text
    assert "No external request was made." in disabled.json()["message"]

    monkeypatch.setattr(settings, "enable_career_page_connector", True)
    monkeypatch.setattr(settings, "greenhouse_boards", "")
    empty = client.post("/api/v1/sources/career_page/sync")
    assert empty.status_code == 422
    assert empty.json()["code"] == "no_boards"
    assert "No external request was made." in empty.json()["message"]

    monkeypatch.setattr(settings, "greenhouse_boards", "../secret|Evil")
    invalid = client.post("/api/v1/sources/career_page/sync")
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "no_boards"
    assert "secret" not in invalid.text


def test_sync_imports_scores_and_repeats_without_duplicates(client, monkeypatch, tmp_path):
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        assert request.method == "GET"
        assert request.url.host == "boards-api.greenhouse.io"
        title = "Backend Engineer" if calls["count"] == 1 else "Backend Engineer II"
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": 9,
                        "title": title,
                        "content": "<p>Requirements: Python.</p>",
                        "location": {"name": "Remote"},
                        "absolute_url": "https://boards.greenhouse.io/fixtureboard/jobs/9",
                    },
                    {"title": "Missing id"},
                ]
            },
        )

    _enable(monkeypatch, tmp_path, f"{TOKEN}|Fixture Co", handler)
    manual = client.post("/api/v1/jobs/import", json=job_payload("manual-stays")).json()
    first = client.post("/api/v1/sources/career_page/sync")
    assert first.status_code == 200
    body = first.json()
    assert body["boards_checked"] == 1
    assert body["jobs_fetched"] == 2
    assert body["jobs_created"] == 1
    assert body["jobs_updated"] == 0
    assert body["duplicates_skipped"] == 0
    assert body["jobs_skipped"] == 1
    assert body["matches_written"] == 1
    assert body["errors"] == []
    assert TOKEN not in first.text
    assert CANARY not in first.text
    assert "candidate@example.com" not in first.text

    _clear_rate_limit(TOKEN)
    second = client.post("/api/v1/sources/career_page/sync")
    assert second.status_code == 200
    assert second.json()["jobs_created"] == 0
    assert second.json()["jobs_updated"] == 1
    assert second.json()["matches_written"] == 1
    assert CANARY not in second.text

    listed = client.get("/api/v1/jobs?origin=discovered").json()
    assert listed["total"] == 1
    discovered = listed["items"][0]
    assert discovered["origin"] == "discovered"
    assert discovered["title"] == "Backend Engineer II"
    assert discovered["company"] == "Fixture Co"
    experience = next(factor for factor in discovered["assessment"]["factors"] if factor["key"] == "experience")
    assert experience["status"] == "unknown"
    assert experience["score"] is None
    assert discovered["assessment"]["threshold"] == 50
    assert discovered["assessment"]["total_score"] is not None
    assert discovered["assessment"]["meets_threshold"] is True
    assert CANARY not in str(listed)
    assert TOKEN not in str(listed)
    assert discovered["source_job_id"] == greenhouse_source_job_id(TOKEN, "9")
    assert discovered["canonical_url"] is None

    manual_rows = client.get("/api/v1/jobs?origin=manual").json()
    assert manual_rows["total"] == 1
    assert manual_rows["items"][0]["id"] == manual["id"]
    assert manual_rows["items"][0]["description"].startswith("Backend software engineer")
    database = MongoClient(settings.mongodb_url)[settings.mongodb_database]
    assert database.jobs.count_documents({"source_job_id": greenhouse_source_job_id(TOKEN, "9")}) == 1
    assert database.job_matches.count_documents({}) == 1
    assert database.applications.count_documents({}) == 0
    _assert_policy(client)


def test_one_board_failure_keeps_jobs_from_the_other_board(client, monkeypatch, tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/v1/boards/{OTHER}/jobs":
            return httpx.Response(404)
        return httpx.Response(
            200,
            json={"jobs": [{"id": 4, "title": "Platform Engineer", "content": "<p>Requirements: Python.</p>", "location": {"name": "Remote"}}]},
        )

    _enable(monkeypatch, tmp_path, f"{OTHER}|Missing Co,{TOKEN}|Fixture Co", handler)
    response = client.post("/api/v1/sources/career_page/sync")
    assert response.status_code == 200
    body = response.json()
    assert body["boards_checked"] == 2
    assert body["jobs_created"] == 1
    assert body["errors"] == [{"code": "board_not_found"}]
    assert OTHER not in response.text
    assert TOKEN not in response.text
    database = MongoClient(settings.mongodb_url)[settings.mongodb_database]
    assert database.jobs.count_documents({"origin": "discovered"}) == 1
    assert database.applications.count_documents({}) == 0

    _clear_rate_limit(TOKEN, OTHER)

    def only_missing(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/v1/boards/{OTHER}/jobs":
            return httpx.Response(404)
        return httpx.Response(200, json={"jobs": []})

    _replace_handler(monkeypatch, only_missing)
    again = client.post("/api/v1/sources/career_page/sync")
    assert again.status_code == 200
    assert again.json()["jobs_created"] == 0
    assert database.jobs.count_documents({"source_job_id": greenhouse_source_job_id(TOKEN, "4"), "status": "active"}) == 1


def test_rate_limit_and_lock_make_no_extra_request(client, monkeypatch, tmp_path):
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json={"jobs": [{"id": 3, "title": "Backend Engineer", "content": "<p>Python</p>"}]})

    _enable(monkeypatch, tmp_path, f"{TOKEN}|Fixture Co", handler)
    assert client.post("/api/v1/sources/career_page/sync").status_code == 200
    blocked = client.post("/api/v1/sources/career_page/sync")
    assert blocked.status_code == 200
    assert blocked.json()["errors"] == [{"code": "rate_limited"}]
    assert blocked.json()["jobs_fetched"] == 0
    assert calls["count"] == 1

    store = _redis()
    store.set("lock:discovery:career_page", "held", nx=True, px=60000)
    try:
        waiting = client.post("/api/v1/sources/career_page/sync")
    finally:
        store.delete("lock:discovery:career_page")
    assert waiting.status_code == 409
    assert waiting.json()["code"] == "sync_in_progress"
    assert calls["count"] == 1
    assert TOKEN not in waiting.text
    assert client.get("/api/v1/applications").json()["total"] == 0
    _assert_policy(client)


def test_profile_error_does_not_drop_the_imported_job_or_leak_the_file(client, monkeypatch, tmp_path):
    secret = tmp_path / "profile.json"
    secret.write_text("{not-json SECRET-PROFILE-BODY", encoding="utf-8")
    monkeypatch.setattr(settings, "profile_path", str(secret))
    monkeypatch.setattr(settings, "resume_storage_path", str(tmp_path))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jobs": [{"id": 8, "title": "Backend Engineer", "content": "<p>Python</p>"}]})

    _enable_boards(monkeypatch, f"{TOKEN}|Fixture Co", handler)
    response = client.post("/api/v1/sources/career_page/sync")
    assert response.status_code == 200
    assert response.json()["jobs_created"] == 1
    assert response.json()["matches_written"] == 0
    assert response.json()["errors"] == [{"code": "profile_invalid"}]
    assert "SECRET-PROFILE-BODY" not in response.text
    assert TOKEN not in response.text
    database = MongoClient(settings.mongodb_url)[settings.mongodb_database]
    assert database.jobs.count_documents({"origin": "discovered"}) == 1
    assert database.applications.count_documents({}) == 0
    _assert_policy(client)


def test_rate_limited_board_does_not_block_an_eligible_board(client, monkeypatch, tmp_path):
    limited = "heldboard"
    ready = "readyboard"
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        assert request.url.host == "boards-api.greenhouse.io"
        assert request.method == "GET"
        if request.url.path == f"/v1/boards/{limited}/jobs":
            raise AssertionError("rate-limited board was fetched")
        return httpx.Response(
            200,
            json={"jobs": [{"id": 15, "title": "Backend Engineer", "content": "<p>Requirements: Python.</p>", "location": {"name": "Remote"}}]},
        )

    _enable(monkeypatch, tmp_path, f"{limited}|Held Co,{ready}|Ready Co", handler)
    _redis().set(greenhouse_rate_limit_key(limited), "1", ex=3600)
    response = client.post("/api/v1/sources/career_page/sync")
    assert response.status_code == 200
    body = response.json()
    assert body["boards_checked"] == 2
    assert body["jobs_fetched"] == 1
    assert body["jobs_created"] == 1
    assert body["errors"] == [{"code": "rate_limited"}]
    assert calls == [f"/v1/boards/{ready}/jobs"]
    assert limited not in response.text
    assert ready not in response.text
    database = MongoClient(settings.mongodb_url)[settings.mongodb_database]
    assert database.jobs.count_documents({"source_job_id": greenhouse_source_job_id(ready, "15"), "origin": "discovered"}) == 1
    assert all(ready not in key and limited not in key for key in _rate_limit_keys())
    _clear_rate_limit(limited, ready)


def test_exception_in_the_board_loop_releases_the_sync_lock(client, monkeypatch, tmp_path):
    calls = {"upserts": 0}
    original = JobRepository.upsert_discovered

    async def fail_once(self, doc):
        calls["upserts"] += 1
        if calls["upserts"] == 1:
            raise RuntimeError("forced sync failure")
        return await original(self, doc)

    monkeypatch.setattr(JobRepository, "upsert_discovered", fail_once)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"jobs": [{"id": 21, "title": "Backend Engineer", "content": "<p>Requirements: Python.</p>"}]},
        )

    _enable(monkeypatch, tmp_path, f"{TOKEN}|Fixture Co", handler)
    # The app returns 500. Starlette's test client also re-raises the endpoint exception.
    with pytest.raises(RuntimeError, match="forced sync failure"):
        client.post("/api/v1/sources/career_page/sync")
    assert _redis().exists("lock:discovery:career_page") == 0

    _clear_rate_limit(TOKEN)
    recovered = client.post("/api/v1/sources/career_page/sync")
    assert recovered.status_code == 200
    assert recovered.json()["jobs_created"] == 1
    assert recovered.json()["errors"] == []
    assert _redis().exists("lock:discovery:career_page") == 0


def test_sync_api_preserves_a_manual_job_with_the_same_source_id(client, monkeypatch, tmp_path):
    seen_at = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
    source_job_id = f"greenhouse:{TOKEN}:42"
    database = MongoClient(settings.mongodb_url)[settings.mongodb_database]
    database.jobs.insert_one(
        {
            "source": "career_page",
            "source_job_id": source_job_id,
            "origin": "manual",
            "company": "Example Co",
            "title": "Do not overwrite",
            "description": "manual collision",
            "canonical_url": "https://jobs.example.com/manual-collision",
            "match_score": 50,
            "status": "active",
            "created_at": seen_at,
            "updated_at": seen_at,
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"jobs": [{"id": 42, "title": "Replacement title", "content": "<p>Should not replace a manual row</p>"}]},
        )

    _enable(monkeypatch, tmp_path, f"{TOKEN}|Fixture Co", handler)
    response = client.post("/api/v1/sources/career_page/sync")
    assert response.status_code == 200
    body = response.json()
    assert body["jobs_created"] == 0
    assert body["jobs_updated"] == 0
    assert body["duplicates_skipped"] == 1
    assert body["matches_written"] == 0
    assert TOKEN not in response.text
    assert database.jobs.count_documents({"source_job_id": source_job_id}) == 0
    stored = database.jobs.find_one({"source_job_id": greenhouse_source_job_id(TOKEN, "42")})
    assert stored["origin"] == "manual"
    assert stored["title"] == "Do not overwrite"
    assert stored["description"] == "manual collision"
    assert stored["company"] == "Example Co"
    assert TOKEN not in client.get("/api/v1/jobs").text


def test_legacy_greenhouse_ids_are_rewritten_without_duplicates_or_token_leaks(client, monkeypatch, tmp_path):
    seen_at = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
    database = MongoClient(settings.mongodb_url)[settings.mongodb_database]
    database.jobs.insert_many(
        [
            {
                "source": "career_page",
                "source_job_id": f"greenhouse:{TOKEN}:9",
                "board_token": TOKEN,
                "origin": "discovered",
                "company": "Fixture Co",
                "title": "Old title",
                "description": "Python",
                "canonical_url": f"https://boards.greenhouse.io/{TOKEN}/jobs/9",
                "status": "active",
                "created_at": seen_at,
                "updated_at": seen_at,
            },
            {
                "source": "career_page",
                "source_job_id": f"greenhouse:{TOKEN}:77",
                "board_token": TOKEN,
                "origin": "discovered",
                "company": "Fixture Co",
                "title": "Kept while absent",
                "description": "Still stored",
                "canonical_url": f"https://boards.greenhouse.io/{TOKEN}/jobs/77?for={TOKEN}",
                "status": "active",
                "created_at": seen_at,
                "updated_at": seen_at,
            },
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": 9,
                        "title": "Updated title",
                        "content": "<p>Requirements: Python.</p>",
                        "absolute_url": f"https://boards.greenhouse.io/{TOKEN}/jobs/9",
                        "location": {"name": "Remote"},
                    }
                ]
            },
        )

    _enable(monkeypatch, tmp_path, f"{TOKEN}|Fixture Co", handler)
    first = client.post("/api/v1/sources/career_page/sync")
    assert first.status_code == 200
    assert first.json()["jobs_created"] == 0
    assert first.json()["jobs_updated"] == 1
    assert TOKEN not in first.text
    assert database.jobs.count_documents({"source": "career_page"}) == 2
    updated = database.jobs.find_one({"source_job_id": greenhouse_source_job_id(TOKEN, "9")})
    assert updated["title"] == "Updated title"
    assert updated.get("board_token") is None
    assert updated["canonical_url"] is None
    absent = database.jobs.find_one({"source_job_id": greenhouse_source_job_id(TOKEN, "77")})
    assert absent["title"] == "Kept while absent"
    assert absent.get("board_token") is None
    assert absent["canonical_url"] is None
    assert database.jobs.count_documents({"source_job_id": f"greenhouse:{TOKEN}:9"}) == 0
    assert TOKEN not in client.get("/api/v1/jobs").text
    assert _rate_limit_keys()
    assert all(TOKEN not in key for key in _rate_limit_keys())

    _clear_rate_limit(TOKEN)
    second = client.post("/api/v1/sources/career_page/sync")
    assert second.status_code == 200
    assert second.json()["jobs_created"] == 0
    assert second.json()["jobs_updated"] == 1
    assert database.jobs.count_documents({"source": "career_page"}) == 2
    assert TOKEN not in second.text


def test_sync_assessment_uses_the_stored_minimum_score(client, monkeypatch, tmp_path):
    saved = client.put(
        "/api/v1/automation/settings",
        json={
            "dry_run": True,
            "automation_enabled": False,
            "minimum_match_score": 80,
            "search_interval_minutes": 60,
            "followup_enabled": True,
            "global_pause": True,
        },
    )
    assert saved.status_code == 200
    assert saved.json()["minimum_match_score"] == 80
    assert saved.json()["dry_run"] is True
    assert saved.json()["automation_enabled"] is False

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": 33,
                        "title": "Accountant",
                        "content": "<p>Requirements: Python.</p>",
                        "location": {"name": "Remote"},
                    }
                ]
            },
        )

    _enable(monkeypatch, tmp_path, f"{TOKEN}|Fixture Co", handler)
    response = client.post("/api/v1/sources/career_page/sync")
    assert response.status_code == 200
    assert response.json()["jobs_created"] == 1
    assert response.json()["matches_written"] == 1
    listed = client.get("/api/v1/jobs?origin=discovered").json()
    assessment = listed["items"][0]["assessment"]
    assert assessment["threshold"] == 80
    assert assessment["total_score"] >= 50
    assert assessment["total_score"] < 80
    assert assessment["meets_threshold"] is False
    assert client.get("/api/v1/automation/settings").json()["minimum_match_score"] == 80


def _enable(monkeypatch, tmp_path, boards: str, handler) -> None:
    resume = tmp_path / "resume.txt"
    resume.write_text(f"{CANARY}\nPython\n", encoding="utf-8")
    profile = tmp_path / "profile.json"
    profile.write_text(
        json.dumps(
            {
                "skills": [{"name": "Python"}],
                "preferred_roles": ["Backend Engineer"],
                "work_arrangement_preferences": ["Remote"],
                "resume_filename": "resume.txt",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "profile_path", str(profile))
    monkeypatch.setattr(settings, "resume_storage_path", str(tmp_path))
    _enable_boards(monkeypatch, boards, handler)


def _enable_boards(monkeypatch, boards: str, handler) -> None:
    _clear_rate_limit(TOKEN, OTHER)
    monkeypatch.setattr(settings, "enable_career_page_connector", True)
    monkeypatch.setattr(settings, "greenhouse_boards", boards)
    _replace_handler(monkeypatch, handler)
    real = GreenhouseRateLimiter

    def without_pause(*args, **kwargs):
        kwargs["min_interval_seconds"] = 0
        return real(*args, **kwargs)

    monkeypatch.setattr("app.services.discovery.GreenhouseRateLimiter", without_pause)


def _replace_handler(monkeypatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("app.services.discovery.httpx.AsyncClient", factory)


def _clear_rate_limit(*tokens: str) -> None:
    store = _redis()
    store.delete(
        "lock:discovery:career_page",
        *(f"ratelimit:greenhouse:{token}" for token in tokens),
        *(greenhouse_rate_limit_key(token) for token in tokens),
    )


def _rate_limit_keys() -> list[str]:
    return [key.decode() if isinstance(key, bytes) else key for key in _redis().scan_iter("ratelimit:greenhouse:*")]


def _redis():
    return redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)


def _assert_policy(client) -> None:
    policy = client.get("/api/v1/automation/settings").json()
    assert policy["dry_run"] is True
    assert policy["automation_enabled"] is False
    assert policy["minimum_match_score"] == 50
    sources = client.get("/api/v1/sources").json()
    career = next(item for item in sources if item["source"] == "career_page")
    assert career["application_supported"] is False
    for name in ("linkedin", "naukri", "wellfound", "gmail"):
        item = next(source for source in sources if source["source"] == name)
        assert item["configured"] is False
        assert item["application_supported"] is False
