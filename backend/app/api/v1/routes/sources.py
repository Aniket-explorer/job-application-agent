from fastapi import APIRouter

from app.services.sources import get_source, list_sources

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("")
async def sources():
    return list_sources()


@router.get("/{source_name}")
async def source(source_name: str):
    return get_source(source_name)
