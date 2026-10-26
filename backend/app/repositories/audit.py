from pymongo.errors import PyMongoError

from app.core.errors import raise_for_database
from app.db.client import get_db
from app.models import utcnow


class AuditRepository:
    @property
    def _events(self):
        return get_db().audit_events

    async def record(self, *, entity_id: str, event: str, details: dict) -> None:
        try:
            await self._events.insert_one(
                {"entity_id": entity_id, "event": event, "details": details, "created_at": utcnow()}
            )
        except PyMongoError as exc:
            raise_for_database(exc)
