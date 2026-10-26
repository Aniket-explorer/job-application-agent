from fastapi import APIRouter

from app.scoring.profile import profile_status

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/status")
async def read_profile_status():
    return profile_status()
