import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from pymongo import MongoClient
from pymongo.asynchronous.collection import AsyncCollection

from app.api.serializers import serialize_job
from app.connectors.career_page.greenhouse import BoardConfig, greenhouse_rate_limit_key, greenhouse_source_job_id
from app.core.config import settings
from app.db.client import get_db, get_redis
from app.db.indexes import ensure_indexes
from app.repositories.jobs import JobRepository
from app.services.discovery import GreenhouseRateLimiter, sync_greenhouse_boards

BOARD = BoardConfig(token="exampleboard", company_name="Example Company")
SEEN_AT = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


class AllowLimiter:
    async def reserve(self, token):
        return True


class OpenLock:
    async def acquire(self):
        return "integration-lock"

    async def release(self, token):
        return None


def test_repeat_sync_updates_discovered_jobs_and_preserves_manual_rows():
    assert settings.mongodb_database == "job_agent_integration_test"
    MongoClient(settings.mongodb_url).drop_database(settings.mongodb_database)
    asyncio.run(_cleanup_redis())
    try:
        asyncio.run(_repeat_sync())
    finally:
        asyncio.run(_cleanup_redis())
        MongoClient(settings.mongodb_url).drop_database(settings.mongodb_database)


def test_legacy_migration_is_retryable_and_preserves_related_records():
    assert settings.mongodb_database == "job_agent_integration_test"
    MongoClient(settings.mongodb_url).drop_database(settings.mongodb_database)
    try:
        asyncio.run(_migration_safety())
    finally:
        MongoClient(settings.mongodb_url).drop_database(settings.mongodb_database)


def test_redis_rate_limit_and_lock_use_the_test_redis():
    asyncio.run(_cleanup_redis())
    try:
        asyncio.run(_limits())
    finally:
        asyncio.run(_cleanup_redis())


async def _repeat_sync():
    await ensure_indexes()
    manual = {
        "source": "manual",
        "source_job_id": "smoke-existing",
        "origin": "manual",
        "company": "Example Co",
        "title": "Backend Engineer",
        "description": "Keep this manual row",
        "canonical_url": "https://jobs.example.com/smoke-existing",
        "match_score": 71.5,
        "status": "active",
        "created_at": SEEN_AT,
        "updated_at": SEEN_AT,
    }
    preserved_key = {
        "source": "career_page",
        "source_job_id": "greenhouse:exampleboard:1",
        "origin": "manual",
        "company": "Example Co",
        "title": "Do not overwrite",
        "description": "manual collision",
        "canonical_url": "https://jobs.example.com/manual-collision",
        "match_score": 50,
        "status": "active",
        "created_at": SEEN_AT,
        "updated_at": SEEN_AT,
    }
    repository = JobRepository()
    await repository.insert_or_get_existing(dict(manual))
    await repository.insert_or_get_existing(dict(preserved_key))
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        title = "Backend Engineer" if calls["count"] == 1 else "Backend Engineer II"
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {"id": 9, "title": title, "content": "<p>Python</p>", "location": {"name": "Bengaluru"}},
                    {"id": 1, "title": "Changed title", "content": "<p>Should not replace a manual row</p>"},
                ]
            },
        )

    first = await _sync(handler, repository, now=SEEN_AT)
    second = await _sync(handler, repository, now=SEEN_AT + timedelta(hours=1))
    assert first.created == 1
    assert first.preserved == 1
    assert second.updated == 1
    assert second.preserved == 1
    rows = await repository._jobs.find({"source": "career_page"}).to_list(length=10)
    discovered = [row for row in rows if row.get("origin") == "discovered"]
    assert len(discovered) == 1
    assert discovered[0]["title"] == "Backend Engineer II"
    assert _utc(discovered[0]["first_seen_at"]) == SEEN_AT
    assert _utc(discovered[0]["last_seen_at"]) == SEEN_AT + timedelta(hours=1)
    assert discovered[0]["source_job_id"] == greenhouse_source_job_id("exampleboard", "9")
    assert "exampleboard" not in discovered[0]["source_job_id"]
    assert discovered[0].get("board_token") is None
    manual_row = await repository._jobs.find_one({"source_job_id": "smoke-existing"})
    assert manual_row["title"] == "Backend Engineer"
    assert manual_row["description"] == "Keep this manual row"
    collision = await repository._jobs.find_one({"source_job_id": greenhouse_source_job_id("exampleboard", "1")})
    assert collision["title"] == "Do not overwrite"
    assert collision["origin"] == "manual"
    assert "exampleboard" not in collision["source_job_id"]
    assert await repository._jobs.count_documents({"source_job_id": "greenhouse:exampleboard:1"}) == 0


async def _migration_safety():
    await ensure_indexes()
    repository = JobRepository()
    database = get_db()
    slug_job = await repository._jobs.insert_one(_legacy_job("9", "https://boards.greenhouse.io/exampleboard/jobs/9", "Slug link"))
    safe_job = await repository._jobs.insert_one(_legacy_job("77", "https://jobs.example.com/keep-77", "Safe link"))
    manual = await repository._jobs.insert_one(
        _legacy_job("1", "https://jobs.example.com/manual-collision", "Do not overwrite", origin="manual")
    )
    application = await database.applications.insert_one(
        {"job_id": str(slug_job.inserted_id), "candidate_id": "default-candidate", "status": "dry_run", "dry_run": True, "channel": "manual", "match_score": 71.5, "created_at": SEEN_AT}
    )
    match = await database.job_matches.insert_one(
        {"job_id": str(slug_job.inserted_id), "candidate_id": "default-candidate", "matching_version": "phase2-v1", "total_score": 81.2}
    )
    original = AsyncCollection.update_one
    state = {"updates": 0}

    async def interrupt_second_job_update(self, *args, **kwargs):
        if getattr(self, "name", "") == "jobs":
            state["updates"] += 1
            if state["updates"] == 2:
                raise RuntimeError("migration interrupted")
        return await original(self, *args, **kwargs)

    AsyncCollection.update_one = interrupt_second_job_update
    try:
        with pytest.raises(RuntimeError, match="migration interrupted"):
            await repository.migrate_legacy_greenhouse_ids()
    finally:
        AsyncCollection.update_one = original

    assert await repository._jobs.count_documents({}) == 3
    assert (await database.applications.find_one({"_id": application.inserted_id}))["job_id"] == str(slug_job.inserted_id)
    assert (await database.job_matches.find_one({"_id": match.inserted_id}))["job_id"] == str(slug_job.inserted_id)
    stored_slug = await repository._jobs.find_one({"_id": slug_job.inserted_id})
    exposed = serialize_job(stored_slug)
    assert exposed["source_job_id"] == greenhouse_source_job_id("exampleboard", "9")
    assert "exampleboard" not in exposed["source_job_id"]
    assert exposed["canonical_url"] is None

    assert await repository.migrate_legacy_greenhouse_ids() >= 1
    assert await repository.migrate_legacy_greenhouse_ids() == 0
    migrated_slug = await repository._jobs.find_one({"_id": slug_job.inserted_id})
    migrated_safe = await repository._jobs.find_one({"_id": safe_job.inserted_id})
    migrated_manual = await repository._jobs.find_one({"_id": manual.inserted_id})
    assert migrated_slug["source_job_id"] == greenhouse_source_job_id("exampleboard", "9")
    assert migrated_slug["canonical_url"] is None
    assert migrated_safe["source_job_id"] == greenhouse_source_job_id("exampleboard", "77")
    assert migrated_safe["canonical_url"] == "https://jobs.example.com/keep-77"
    assert migrated_manual["origin"] == "manual"
    assert migrated_manual["title"] == "Do not overwrite"
    assert migrated_manual["canonical_url"] == "https://jobs.example.com/manual-collision"
    assert migrated_manual["source_job_id"] == greenhouse_source_job_id("exampleboard", "1")
    assert (await database.applications.find_one({"_id": application.inserted_id}))["job_id"] == str(slug_job.inserted_id)
    assert (await database.job_matches.find_one({"_id": match.inserted_id}))["total_score"] == 81.2

    survivor = await repository._jobs.insert_one(_hashed_job("3", "Hashed survivor"))
    duplicate = await repository._jobs.insert_one(_legacy_job("3", "https://boards.greenhouse.io/exampleboard/jobs/3", "Legacy duplicate"))
    await database.applications.insert_one(
        {"job_id": str(duplicate.inserted_id), "candidate_id": "other", "status": "dry_run", "dry_run": True, "channel": "manual", "match_score": 10, "created_at": SEEN_AT}
    )
    await repository.migrate_legacy_greenhouse_ids()
    kept = await repository._jobs.find_one({"_id": duplicate.inserted_id})
    assert kept is not None
    assert kept["canonical_url"] is None
    assert (await repository._jobs.find_one({"_id": survivor.inserted_id}))["title"] == "Hashed survivor"
    hidden = serialize_job(kept)
    assert hidden["source_job_id"] == greenhouse_source_job_id("exampleboard", "3")
    assert "exampleboard" not in hidden["source_job_id"]

    await repository._jobs.insert_one(_hashed_job("4", "Only hashed"))
    await repository._jobs.insert_one(_legacy_job("4", "https://boards.greenhouse.io/exampleboard/jobs/4", "Unreferenced legacy"))
    await repository.migrate_legacy_greenhouse_ids()
    assert await repository._jobs.count_documents({"source_job_id": "greenhouse:exampleboard:4"}) == 0
    assert await repository._jobs.count_documents({"source_job_id": greenhouse_source_job_id("exampleboard", "4")}) == 1


def _legacy_job(job_id: str, canonical_url: str, title: str, *, origin: str = "discovered") -> dict:
    return {
        "source": "career_page",
        "source_job_id": f"greenhouse:exampleboard:{job_id}",
        "board_token": "exampleboard",
        "origin": origin,
        "company": "Example Company",
        "title": title,
        "description": "Python",
        "canonical_url": canonical_url,
        "status": "active",
        "created_at": SEEN_AT,
        "updated_at": SEEN_AT,
    }


def _hashed_job(job_id: str, title: str) -> dict:
    return {
        "source": "career_page",
        "source_job_id": greenhouse_source_job_id("exampleboard", job_id),
        "board_digest": "stored-digest",
        "origin": "discovered",
        "company": "Example Company",
        "title": title,
        "description": "Python",
        "canonical_url": "https://jobs.example.com/hashed",
        "status": "active",
        "created_at": SEEN_AT,
        "updated_at": SEEN_AT,
    }


async def _limits():
    redis = get_redis()
    limiter = GreenhouseRateLimiter(redis, min_interval_seconds=0, window_seconds=3600)
    assert await limiter.reserve("exampleboard") is True
    assert await limiter.reserve("exampleboard") is False
    held = await redis.set("lock:discovery:career_page", "held", nx=True, px=60000)
    assert held
    def fail_if_called(request: httpx.Request) -> httpx.Response:
        raise AssertionError("fetched while locked")

    blocked = await sync_greenhouse_boards(
        enabled=True,
        boards=[BOARD],
        transport=httpx.MockTransport(fail_if_called),
        jobs=JobRepository(),
        rate_limiter=AllowLimiter(),
    )
    assert blocked.status == "already_running"


async def _sync(handler, repository, *, now=SEEN_AT):
    return await sync_greenhouse_boards(
        enabled=True,
        boards=[BOARD],
        transport=httpx.MockTransport(handler),
        jobs=repository,
        lock=OpenLock(),
        rate_limiter=AllowLimiter(),
        sleep=_noop_sleep,
        now=now,
        max_retries=0,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def _noop_sleep(seconds):
    return None


async def _cleanup_redis():
    redis = get_redis()
    await redis.delete(
        "ratelimit:greenhouse:exampleboard",
        greenhouse_rate_limit_key("exampleboard"),
        "lock:discovery:career_page",
    )
