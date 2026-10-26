from app.core.errors import PolicyViolationError
from app.models import AutomationSettings, utcnow
from app.repositories.settings import SettingsRepository

_LIVE_MODE_MESSAGE = "Live mode is not implemented. Keep dry_run=true until provider-specific controls and tests exist."


class SettingsService:
    def __init__(self, repository: SettingsRepository | None = None) -> None:
        self._repository = repository or SettingsRepository()

    async def get(self) -> AutomationSettings:
        return await self._repository.load_or_seed()

    async def update(self, payload: AutomationSettings) -> AutomationSettings:
        if payload.dry_run is not True:
            raise PolicyViolationError(_LIVE_MODE_MESSAGE)
        if payload.automation_enabled:
            raise PolicyViolationError("Automation cannot be enabled until a permitted channel is implemented and tested.")
        safe = payload.model_copy(update={"dry_run": True, "automation_enabled": False})
        return await self._repository.save(safe, updated_at=utcnow())
