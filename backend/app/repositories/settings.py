from datetime import datetime

from pymongo.errors import PyMongoError

from app.core.config import Settings, settings
from app.core.errors import raise_for_database
from app.db.client import get_db
from app.db.indexes import SETTINGS_ID
from app.models import AutomationSettings, utcnow


def default_settings(config: Settings | None = None) -> AutomationSettings:
    """Seed values. Live submission stays off even if the environment asks for it."""
    config = config or settings
    return AutomationSettings(
        dry_run=True,
        automation_enabled=False,
        minimum_match_score=config.min_match_score,
        search_interval_minutes=config.discovery_interval_minutes,
        followup_enabled=True,
        global_pause=config.global_pause,
    )


class SettingsRepository:
    @property
    def _settings(self):
        return get_db().automation_settings

    async def get(self) -> AutomationSettings | None:
        try:
            doc = await self._settings.find_one({"_id": SETTINGS_ID})
        except PyMongoError as exc:
            raise_for_database(exc)
        if doc is None:
            return None
        parsed = AutomationSettings.model_validate(doc)
        return parsed.model_copy(update={"dry_run": True, "automation_enabled": False})

    async def load_or_seed(self) -> AutomationSettings:
        current = await self.get()
        if current is not None:
            return current
        seeded = default_settings()
        await self.save(seeded, updated_at=utcnow())
        stored = await self.get()
        return stored if stored is not None else seeded

    async def save(self, payload: AutomationSettings, updated_at: datetime) -> AutomationSettings:
        # replace_one would let a caller persist dry_run=false. Force the safe values here too.
        safe = payload.model_copy(update={"dry_run": True, "automation_enabled": False})
        doc = safe.model_dump()
        doc["_id"] = SETTINGS_ID
        doc["updated_at"] = updated_at
        try:
            await self._settings.replace_one({"_id": SETTINGS_ID}, doc, upsert=True)
        except PyMongoError as exc:
            raise_for_database(exc)
        return safe
