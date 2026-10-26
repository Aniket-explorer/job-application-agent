from fastapi import APIRouter

from app.models import AutomationSettings
from app.services.settings import SettingsService

router = APIRouter(prefix="/automation", tags=["automation"])
_settings = SettingsService()


@router.get("/settings")
async def get_settings():
    return (await _settings.get()).model_dump()


@router.put("/settings")
async def update_settings(payload: AutomationSettings):
    return (await _settings.update(payload)).model_dump()
