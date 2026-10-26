from fastapi import APIRouter

from app.connectors.career_page.greenhouse import parse_greenhouse_boards
from app.core.config import settings
from app.core.errors import AppError
from app.services.discovery import sync_greenhouse_boards, sync_summary
from app.services.scoring import ScoringService
from app.services.sources import get_source, list_sources

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("")
async def sources():
    return list_sources()


@router.post("/career_page/sync")
async def sync_career_page():
    """Run one Greenhouse list sync. Disabled configuration makes no external request."""
    if not settings.enable_career_page_connector:
        raise AppError(
            "connector_disabled",
            422,
            "Greenhouse discovery is disabled. No external request was made.",
        )
    boards = parse_greenhouse_boards(settings.greenhouse_boards)
    if not boards:
        raise AppError(
            "no_boards",
            422,
            "No Greenhouse boards are configured. No external request was made.",
        )
    result = await sync_greenhouse_boards(enabled=True, boards=boards, allow_network=True, scorer=_score_discovered)
    if result.status == "already_running":
        raise AppError(
            "sync_in_progress",
            409,
            "A career page sync is already running. No additional request was made.",
        )
    return sync_summary(result)


async def _score_discovered(job: dict) -> str | None:
    """Score one discovered job. Profile errors stay as codes and do not include resume text."""
    try:
        await ScoringService().score_job(str(job["_id"]))
    except AppError as exc:
        return exc.code
    return None


@router.get("/{source_name}")
async def source(source_name: str):
    return get_source(source_name)
