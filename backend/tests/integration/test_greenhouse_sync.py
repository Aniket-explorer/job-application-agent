import asyncio
from datetime import datetime, timedelta, timezone

import httpx
from pymongo import MongoClient

from app.connectors.career_page.greenhouse import BoardConfig
from app.core.config import settings
from app.db.client import get_redis
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
    assert discovered[0]["source_job_id"] == "greenhouse:exampleboard:9"
    manual_row = await repository._jobs.find_one({"source_job_id": "smoke-existing"})
    assert manual_row["title"] == "Backend Engineer"
    assert manual_row["description"] == "Keep this manual row"
    collision = await repository._jobs.find_one({"source_job_id": "greenhouse:exampleboard:1"})
    assert collision["title"] == "Do not overwrite"
    assert collision["origin"] == "manual"


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
    await redis.delete("ratelimit:greenhouse:exampleboard", "lock:discovery:career_page")
