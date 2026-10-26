import uuid
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from app.connectors.career_page.greenhouse import (
    BoardConfig,
    BoardError,
    GreenhouseClient,
    normalize_greenhouse_job,
    parse_greenhouse_boards,
    select_boards,
)
from app.core.config import settings
from app.db.client import get_redis
from app.models import utcnow
from app.repositories.jobs import JobRepository

_LOCK_NAME = "career_page"
_RELEASE_LOCK = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


@dataclass
class BoardSyncResult:
    error_code: str | None = None
    fetched: int = 0
    created: int = 0
    updated: int = 0
    preserved: int = 0
    skipped: int = 0
    scored: int = 0
    scoring_errors: list[str] = field(default_factory=list)


@dataclass
class SyncResult:
    status: str
    fetched: int = 0
    created: int = 0
    updated: int = 0
    preserved: int = 0
    skipped: int = 0
    scored: int = 0
    boards_attempted: int = 0
    boards_dropped_by_cap: int = 0
    scoring_errors: list[str] = field(default_factory=list)
    boards: list[BoardSyncResult] = field(default_factory=list)


class GreenhouseRateLimiter:
    """One list request per board per hour, with a pause between boards."""

    def __init__(
        self,
        redis_client=None,
        *,
        min_interval_seconds: float = 2.0,
        window_seconds: int = 3600,
        clock=None,
        sleep=None,
    ):
        self._redis = redis_client
        self._min_interval_seconds = min_interval_seconds
        self._window_seconds = window_seconds
        self._clock = clock or _monotonic
        self._sleep = sleep or _async_sleep
        self._last_at: float | None = None

    async def reserve(self, token: str) -> bool:
        now = self._clock()
        if self._last_at is not None:
            wait = self._min_interval_seconds - (now - self._last_at)
            if wait > 0:
                await self._sleep(wait)
                now = self._clock()
        self._last_at = now
        redis = self._redis if self._redis is not None else get_redis()
        stored = await redis.set(f"ratelimit:greenhouse:{token}", "1", nx=True, ex=self._window_seconds)
        return bool(stored)


class DiscoveryLock:
    def __init__(self, redis_client=None, *, ttl_ms: int = 900_000):
        self._redis = redis_client
        self._ttl_ms = ttl_ms

    async def acquire(self) -> str | None:
        token = uuid.uuid4().hex
        redis = self._redis if self._redis is not None else get_redis()
        stored = await redis.set(f"lock:discovery:{_LOCK_NAME}", token, nx=True, px=self._ttl_ms)
        if not stored:
            return None
        return token

    async def release(self, token: str) -> None:
        redis = self._redis if self._redis is not None else get_redis()
        await redis.eval(_RELEASE_LOCK, 1, f"lock:discovery:{_LOCK_NAME}", token)


async def sync_greenhouse_boards(
    *,
    enabled: bool | None = None,
    boards: list[BoardConfig] | None = None,
    transport: httpx.BaseTransport | None = None,
    allow_network: bool = False,
    rate_limiter: GreenhouseRateLimiter | None = None,
    lock: DiscoveryLock | None = None,
    jobs: JobRepository | None = None,
    scorer=None,
    sleep=None,
    now: datetime | None = None,
    max_retries: int = 3,
) -> SyncResult:
    """Import published Greenhouse jobs. Does nothing unless this call is explicitly enabled."""
    if enabled is None:
        enabled = settings.enable_career_page_connector
    if not enabled:
        return SyncResult(status="disabled")
    selected_source = boards if boards is not None else parse_greenhouse_boards(settings.greenhouse_boards)
    selected, dropped = select_boards(selected_source)
    if not selected:
        return SyncResult(status="no_boards", boards_dropped_by_cap=dropped)
    if transport is None and not allow_network:
        raise RuntimeError("Greenhouse network calls are disabled for this sync")

    limiter = rate_limiter or GreenhouseRateLimiter(sleep=sleep)
    sync_lock = lock or DiscoveryLock()
    repository = jobs or JobRepository()
    seen_at = now or utcnow()
    lock_token = await sync_lock.acquire()
    if lock_token is None:
        return SyncResult(status="already_running", boards_dropped_by_cap=dropped)

    result = SyncResult(status="completed", boards_dropped_by_cap=dropped)
    try:
        async with httpx.AsyncClient(transport=transport, follow_redirects=False) as http:
            client = GreenhouseClient(http, max_retries=max_retries, sleep=sleep)
            for board in selected:
                board_result = await _sync_board(client, limiter, repository, board, seen_at, scorer)
                result.boards.append(board_result)
                result.boards_attempted += 1
                result.fetched += board_result.fetched
                result.created += board_result.created
                result.updated += board_result.updated
                result.preserved += board_result.preserved
                result.skipped += board_result.skipped
                result.scored += board_result.scored
                for code in board_result.scoring_errors:
                    if code not in result.scoring_errors:
                        result.scoring_errors.append(code)
    finally:
        await sync_lock.release(lock_token)
    return result


async def _sync_board(client, limiter, repository, board: BoardConfig, seen_at: datetime, scorer) -> BoardSyncResult:
    allowed = await limiter.reserve(board.token)
    if not allowed:
        return BoardSyncResult(error_code="rate_limited")
    try:
        raw_jobs = await client.fetch_jobs(board.token)
    except BoardError as exc:
        return BoardSyncResult(error_code=exc.code)
    outcome = BoardSyncResult(fetched=len(raw_jobs))
    for raw in raw_jobs:
        normalized = normalize_greenhouse_job(raw, board, seen_at=seen_at)
        if normalized is None:
            outcome.skipped += 1
            continue
        stored, action = await repository.upsert_discovered(normalized)
        if action == "created":
            outcome.created += 1
        elif action == "updated":
            outcome.updated += 1
        elif action == "preserved":
            outcome.preserved += 1
        if scorer is not None and action in {"created", "updated"}:
            failure = await scorer(stored)
            if failure:
                if failure not in outcome.scoring_errors:
                    outcome.scoring_errors.append(failure)
            else:
                outcome.scored += 1
    return outcome


def sync_summary(result: SyncResult) -> dict:
    """Counts for an API response. Board tokens and resume text are not included."""
    errors = [{"code": board.error_code} for board in result.boards if board.error_code]
    errors.extend({"code": code} for code in result.scoring_errors)
    return {
        "status": result.status,
        "boards_checked": result.boards_attempted,
        "jobs_fetched": result.fetched,
        "jobs_created": result.created,
        "jobs_updated": result.updated,
        "duplicates_skipped": result.preserved,
        "jobs_skipped": result.skipped,
        "matches_written": result.scored,
        "errors": errors,
    }


def _monotonic() -> float:
    import time

    return time.monotonic()


async def _async_sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
