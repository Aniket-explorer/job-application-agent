import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from app.connectors.career_page.greenhouse import (
    MAX_BOARDS_PER_SYNC,
    BoardConfig,
    ConnectorUnavailable,
    canonicalize_url,
    normalize_greenhouse_job,
    parse_greenhouse_boards,
)
from app.connectors.stubs import CONNECTORS
from app.core.config import settings
from app.services.discovery import DiscoveryLock, GreenhouseRateLimiter, sync_greenhouse_boards, sync_summary

SEEN_AT = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
BOARD = BoardConfig(token="exampleboard", company_name="Example Company")


class MemoryJobs:
    def __init__(self):
        self.docs = {}

    async def upsert_discovered(self, doc):
        key = (doc["source"], doc["source_job_id"])
        existing = self.docs.get(key)
        if existing is None:
            stored = dict(doc)
            self.docs[key] = stored
            return stored, "created"
        if existing.get("origin") == "manual" or existing.get("source") == "manual":
            return existing, "preserved"
        existing.update(
            {
                "title": doc["title"],
                "description": doc["description"],
                "last_seen_at": doc["last_seen_at"],
                "updated_at": doc["updated_at"],
                "content_hash": doc["content_hash"],
            }
        )
        return existing, "updated"


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def set(self, key, value, nx=False, ex=None, px=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def eval(self, script, numkeys, key, token):
        if self.values.get(key) == token:
            del self.values[key]
            return 1
        return 0


class Clock:
    def __init__(self):
        self.now = 0.0
        self.slept = []

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def test_parser_keeps_only_valid_boards():
    parsed = parse_greenhouse_boards(
        " exampleboard|Example Company, ../secret|Evil, missing-company, ok-board|Second Company, exampleboard|Duplicate "
    )
    assert [(board.token, board.company_name) for board in parsed] == [
        ("exampleboard", "Example Company"),
        ("ok-board", "Second Company"),
    ]


def test_normalize_maps_documented_fields_and_leaves_gaps_empty():
    job = normalize_greenhouse_job(
        {
            "id": 127817,
            "title": " Backend Engineer ",
            "updated_at": "2016-01-14T10:55:28-05:00",
            "absolute_url": "https://boards.greenhouse.io/exampleboard/jobs/127817?utm_source=x&b=2&a=1#frag",
            "location": {"name": " NYC "},
            "content": "&lt;p&gt;Build APIs&lt;/p&gt;",
        },
        BOARD,
        seen_at=SEEN_AT,
    )
    assert job["source"] == "career_page"
    assert job["source_job_id"] == "greenhouse:exampleboard:127817"
    assert job["origin"] == "discovered"
    assert job["company"] == "Example Company"
    assert job["title"] == "Backend Engineer"
    assert job["description"] == "Build APIs"
    assert job["location"] == "NYC"
    assert job["canonical_url"] == "https://boards.greenhouse.io/exampleboard/jobs/127817?a=1&b=2"
    assert job["posted_at"] == datetime(2016, 1, 14, 15, 55, 28, tzinfo=timezone.utc)
    assert job["first_seen_at"] == SEEN_AT
    assert job["last_seen_at"] == SEEN_AT
    assert "salary_min" not in job
    assert "remote_type" not in job


def test_normalize_skips_incomplete_posts_and_unsafe_urls():
    assert normalize_greenhouse_job({"title": "No id"}, BOARD, seen_at=SEEN_AT) is None
    assert normalize_greenhouse_job({"id": 1}, BOARD, seen_at=SEEN_AT) is None
    job = normalize_greenhouse_job(
        {"id": "abc", "title": "Role", "absolute_url": "javascript:alert(1)"},
        BOARD,
        seen_at=SEEN_AT,
    )
    assert job["description"] is None
    assert job["location"] is None
    assert job["posted_at"] is None
    assert job["canonical_url"] is None
    assert canonicalize_url("http://jobs.example.com/role/") == "https://jobs.example.com/role"


def test_career_page_stays_disabled_and_hides_board_configuration(monkeypatch):
    monkeypatch.setattr(settings, "enable_career_page_connector", False)
    monkeypatch.setattr(settings, "greenhouse_boards", "exampleboard|Example Company")
    connector = CONNECTORS["career_page"]
    capabilities = connector.capabilities()
    assert capabilities.configured is False
    assert capabilities.discovery_supported is False
    assert capabilities.application_supported is False
    assert "exampleboard" not in capabilities.note
    assert "Example Company" not in capabilities.note
    with pytest.raises(ConnectorUnavailable):
        asyncio.run(connector.discover_jobs())

    monkeypatch.setattr(settings, "enable_career_page_connector", True)
    enabled = connector.capabilities()
    assert enabled.discovery_supported is True
    assert enabled.application_supported is False
    assert "exampleboard" not in enabled.note
    with pytest.raises(PermissionError):
        asyncio.run(connector.apply({}, {}))


def test_disabled_sync_does_not_call_greenhouse():
    def fail_if_called(request):
        raise AssertionError(request.url)

    result = asyncio.run(
        sync_greenhouse_boards(
            enabled=False,
            boards=[BOARD],
            transport=httpx.MockTransport(fail_if_called),
            jobs=MemoryJobs(),
            lock=_OpenLock(),
            rate_limiter=_AllowLimiter(),
        )
    )
    assert result.status == "disabled"
    assert result.created == 0


def test_sync_refuses_an_implicit_live_call():
    with pytest.raises(RuntimeError):
        asyncio.run(sync_greenhouse_boards(enabled=True, boards=[BOARD], jobs=MemoryJobs(), lock=_OpenLock()))


def test_successful_empty_malformed_and_duplicate_imports():
    jobs = MemoryJobs()
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "GET"
        assert request.url.host == "boards-api.greenhouse.io"
        assert request.url.params["content"] == "true"
        assert request.url.path == "/v1/boards/exampleboard/jobs"
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "jobs": [
                        {"id": 1, "title": "Backend Engineer", "content": "<p>Python</p>", "location": {"name": "Remote"}},
                        {"title": "Missing id"},
                        "not-a-job",
                    ]
                },
            )
        return httpx.Response(200, json={"jobs": [{"id": 1, "title": "Backend Engineer II", "content": "<p>Python</p>"}]})

    first = asyncio.run(_sync(handler, jobs))
    second = asyncio.run(_sync(handler, jobs))
    assert first.created == 1
    assert first.skipped == 2
    assert second.created == 0
    assert second.updated == 1
    assert len(jobs.docs) == 1
    stored = next(iter(jobs.docs.values()))
    assert stored["title"] == "Backend Engineer II"
    assert stored["origin"] == "discovered"
    assert all(call.method == "GET" for call in calls)

    empty = asyncio.run(_sync(lambda request: httpx.Response(200, json={"jobs": []}), MemoryJobs()))
    assert empty.created == 0
    assert empty.boards[0].error_code is None

    malformed = asyncio.run(_sync(lambda request: httpx.Response(200, json={"jobs": "nope"}), MemoryJobs()))
    assert malformed.boards[0].error_code == "malformed_response"


def test_http_errors_timeouts_and_retries_do_not_follow_redirects():
    sleeps = []

    async def record_sleep(seconds):
        sleeps.append(seconds)

    attempts = {"count": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(503, headers={"retry-after": "7"})
        return httpx.Response(200, json={"jobs": [{"id": 5, "title": "Recovered"}]})

    recovered = asyncio.run(_sync(flaky, MemoryJobs(), sleep=record_sleep))
    assert recovered.created == 1
    assert sleeps == [7.0, 7.0]
    assert attempts["count"] == 3

    def time_out(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    timed = asyncio.run(_sync(time_out, MemoryJobs(), sleep=record_sleep, max_retries=2))
    assert timed.boards[0].error_code == "timeout"

    def missing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    not_found = asyncio.run(_sync(missing, MemoryJobs(), sleep=record_sleep))
    assert not_found.boards[0].error_code == "board_not_found"

    def redirect(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://evil.example/jobs"})

    redirected = asyncio.run(_sync(redirect, MemoryJobs(), sleep=record_sleep))
    assert redirected.boards[0].error_code == "unexpected_redirect"


def test_board_cap_and_rate_limit_spacing():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json={"jobs": []})

    boards = [BoardConfig(token=f"board{index}", company_name=f"Company {index}") for index in range(MAX_BOARDS_PER_SYNC + 1)]
    result = asyncio.run(_sync(handler, MemoryJobs(), boards=boards))
    assert result.boards_attempted == MAX_BOARDS_PER_SYNC
    assert result.boards_dropped_by_cap == 1
    assert len(seen) == MAX_BOARDS_PER_SYNC

    clock = Clock()
    limiter = GreenhouseRateLimiter(FakeRedis(), min_interval_seconds=2, clock=clock, sleep=clock.sleep)
    assert asyncio.run(limiter.reserve("exampleboard")) is True
    assert asyncio.run(limiter.reserve("otherboard")) is True
    assert clock.slept == [2.0]
    assert asyncio.run(limiter.reserve("exampleboard")) is False


def test_scorer_runs_only_for_discovered_rows_and_the_summary_hides_the_board_token():
    jobs = MemoryJobs()
    jobs.docs[("career_page", "greenhouse:exampleboard:1")] = {
        "source": "career_page",
        "source_job_id": "greenhouse:exampleboard:1",
        "origin": "manual",
        "title": "Keep manual",
    }
    scored = []

    async def scorer(job):
        scored.append(job["title"])
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {"id": 1, "title": "Should stay manual"},
                    {"id": 2, "title": "Imported", "content": "<p>Python</p>"},
                    {"title": "incomplete"},
                ]
            },
        )

    result = asyncio.run(
        sync_greenhouse_boards(
            enabled=True,
            boards=[BOARD],
            transport=httpx.MockTransport(handler),
            jobs=jobs,
            lock=_OpenLock(),
            rate_limiter=_AllowLimiter(),
            scorer=scorer,
            now=SEEN_AT,
        )
    )
    summary = sync_summary(result)
    assert summary["boards_checked"] == 1
    assert summary["jobs_fetched"] == 3
    assert summary["jobs_created"] == 1
    assert summary["jobs_updated"] == 0
    assert summary["duplicates_skipped"] == 1
    assert summary["jobs_skipped"] == 1
    assert summary["matches_written"] == 1
    assert summary["errors"] == []
    assert scored == ["Imported"]
    assert "exampleboard" not in str(summary)
    assert jobs.docs[("career_page", "greenhouse:exampleboard:1")]["title"] == "Keep manual"


def test_lock_blocks_a_second_sync_and_releases():
    redis = FakeRedis()
    lock = DiscoveryLock(redis)
    token = asyncio.run(lock.acquire())
    assert token
    blocked = asyncio.run(
        sync_greenhouse_boards(
            enabled=True,
            boards=[BOARD],
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"jobs": []})),
            jobs=MemoryJobs(),
            lock=lock,
            rate_limiter=_AllowLimiter(),
        )
    )
    assert blocked.status == "already_running"
    asyncio.run(lock.release(token))
    assert "lock:discovery:career_page" not in redis.values
    opened = asyncio.run(_sync(lambda request: httpx.Response(200, json={"jobs": []}), MemoryJobs(), lock=lock))
    assert opened.status == "completed"


class _AllowLimiter:
    async def reserve(self, token):
        return True


class _OpenLock:
    async def acquire(self):
        return "test-lock"

    async def release(self, token):
        return None


def _sync(handler, jobs, *, boards=None, sleep=None, max_retries=3, lock=None):
    async def noop_sleep(seconds):
        return None

    return sync_greenhouse_boards(
        enabled=True,
        boards=boards or [BOARD],
        transport=httpx.MockTransport(handler),
        jobs=jobs,
        lock=lock or _OpenLock(),
        rate_limiter=_AllowLimiter(),
        sleep=sleep or noop_sleep,
        now=SEEN_AT,
        max_retries=max_retries,
    )
