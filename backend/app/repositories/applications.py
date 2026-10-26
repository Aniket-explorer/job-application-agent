from bson import ObjectId
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.errors import DuplicateError, raise_for_database
from app.db.client import get_db


class ApplicationRepository:
    @property
    def _applications(self):
        return get_db().applications

    async def insert_or_get_existing(self, doc: dict) -> tuple[dict, bool]:
        try:
            result = await self._applications.insert_one(doc)
        except DuplicateKeyError:
            existing = await self._applications.find_one({"job_id": doc["job_id"], "candidate_id": doc["candidate_id"]})
            if existing is None:
                raise DuplicateError("Duplicate application could not be reloaded") from None
            return existing, False
        except PyMongoError as exc:
            raise_for_database(exc)
        doc["_id"] = result.inserted_id
        return doc, True

    async def list_applications(self, *, skip: int, limit: int) -> tuple[list[dict], int]:
        try:
            total = await self._applications.count_documents({})
            cursor = self._applications.find().sort("created_at", -1).skip(skip).limit(limit)
            return await cursor.to_list(length=limit), total
        except PyMongoError as exc:
            raise_for_database(exc)

    async def get(self, application_id: str) -> dict | None:
        if not ObjectId.is_valid(application_id):
            return None
        try:
            return await self._applications.find_one({"_id": ObjectId(application_id)})
        except PyMongoError as exc:
            raise_for_database(exc)
