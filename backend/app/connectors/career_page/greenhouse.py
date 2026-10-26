import hashlib
import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import httpx

GREENHOUSE_ORIGIN = "https://boards-api.greenhouse.io"
BOARD_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
MAX_BOARDS_PER_SYNC = 25
MAX_COMPANY_NAME_LENGTH = 200
_TRACKING_PARAMS = {"ref", "trk", "trackingid", "src", "gclid", "fbclid"}
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class BoardError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ConnectorUnavailable(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class BoardConfig:
    token: str
    company_name: str


def parse_greenhouse_boards(raw: str) -> list[BoardConfig]:
    """Parse `token|Company Name` pairs. Invalid pairs are dropped, not guessed."""
    boards: list[BoardConfig] = []
    seen: set[str] = set()
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        token, separator, company = item.partition("|")
        token = token.strip()
        company = company.strip()
        if separator != "|" or not BOARD_TOKEN_RE.fullmatch(token):
            continue
        if not company or len(company) > MAX_COMPANY_NAME_LENGTH:
            continue
        if token in seen:
            continue
        seen.add(token)
        boards.append(BoardConfig(token=token, company_name=company))
    return boards


def select_boards(boards: list[BoardConfig]) -> tuple[list[BoardConfig], int]:
    selected = boards[:MAX_BOARDS_PER_SYNC]
    return selected, len(boards) - len(selected)


def normalize_greenhouse_job(raw: Any, board: BoardConfig, *, seen_at: datetime) -> dict | None:
    """Map one Greenhouse job post. Missing fields stay null. Incomplete posts are skipped."""
    if not isinstance(raw, dict):
        return None
    job_id = _job_id(raw.get("id"))
    title = raw.get("title")
    if job_id is None or not isinstance(title, str) or not title.strip():
        return None
    title = title.strip()
    description = _description(raw.get("content"))
    location = _location_name(raw.get("location"))
    posted_at = _posted_at(raw)
    canonical_url = canonicalize_url(raw.get("absolute_url"))
    description_hash = hashlib.sha256((description or "").encode("utf-8")).hexdigest()
    return {
        "source": "career_page",
        "source_job_id": f"greenhouse:{board.token}:{job_id}",
        "provider": "greenhouse",
        "board_token": board.token,
        "origin": "discovered",
        "company": board.company_name,
        "company_normalized": board.company_name.casefold(),
        "title": title,
        "title_normalized": title.casefold(),
        "description": description,
        "location": location,
        "location_normalized": location.casefold() if location else None,
        "canonical_url": canonical_url,
        "posted_at": posted_at,
        "content_hash": description_hash,
        "first_seen_at": seen_at,
        "last_seen_at": seen_at,
        "status": "active",
        "created_at": seen_at,
        "updated_at": seen_at,
    }


def canonicalize_url(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parts = urlsplit(value.strip())
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return None
    query = []
    for key, item in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower().startswith("utm_") or key.lower() in _TRACKING_PARAMS:
            continue
        query.append((key, item))
    query.sort()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", parts.netloc.casefold(), path, urlencode(query), ""))


class GreenhouseClient:
    """GET the public job list for one board. This client has no submission method."""

    def __init__(self, http: httpx.AsyncClient, *, max_retries: int = 3, sleep=None):
        self._http = http
        self._max_retries = max_retries
        self._sleep = sleep or _async_sleep

    async def fetch_jobs(self, token: str) -> list[dict]:
        if not BOARD_TOKEN_RE.fullmatch(token):
            raise BoardError("invalid_token")
        url = f"{GREENHOUSE_ORIGIN}/v1/boards/{quote(token, safe='')}/jobs"
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._http.get(
                    url,
                    params={"content": "true"},
                    follow_redirects=False,
                    timeout=httpx.Timeout(15.0, connect=5.0),
                )
            except httpx.TimeoutException:
                if attempt >= self._max_retries:
                    raise BoardError("timeout") from None
                await self._sleep(_backoff(attempt))
                continue
            except httpx.TransportError:
                if attempt >= self._max_retries:
                    raise BoardError("transport_error") from None
                await self._sleep(_backoff(attempt))
                continue
            if response.status_code in {301, 302, 303, 307, 308}:
                raise BoardError("unexpected_redirect")
            if response.status_code == 404:
                raise BoardError("board_not_found")
            if response.status_code in _RETRYABLE_STATUS:
                if attempt >= self._max_retries:
                    code = "rate_limited" if response.status_code == 429 else "http_error"
                    raise BoardError(code)
                await self._sleep(_retry_after(response, attempt))
                continue
            if response.status_code != 200:
                raise BoardError("http_error")
            return _jobs_from_body(response)
        raise BoardError("http_error")


def _jobs_from_body(response: httpx.Response) -> list[dict]:
    try:
        payload = response.json()
    except ValueError:
        raise BoardError("malformed_response") from None
    if not isinstance(payload, dict):
        raise BoardError("malformed_response")
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise BoardError("malformed_response")
    return jobs


def _job_id(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _location_name(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    name = value.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _description(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value
    for _ in range(2):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    text = _TAG_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text).strip()
    return text or None


def _posted_at(raw: dict) -> datetime | None:
    if "first_published" in raw:
        parsed = _parse_time(raw.get("first_published"))
        if parsed is not None:
            return parsed
    if "updated_at" in raw:
        return _parse_time(raw.get("updated_at"))
    return None


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _backoff(attempt: int) -> float:
    return float(min(2 ** (attempt + 1), 30))


def _retry_after(response: httpx.Response, attempt: int) -> float:
    header = response.headers.get("retry-after", "")
    if header.isdigit():
        return float(min(int(header), 30))
    return _backoff(attempt)


async def _async_sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
