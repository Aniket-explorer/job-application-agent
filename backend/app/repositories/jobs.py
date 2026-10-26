from bson import ObjectId
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.errors import DuplicateError, raise_for_database
from app.db.client import get_db


class JobRepository:
    @property
    def _jobs(self):
        return get_db().jobs

    async def insert_or_get_existing(self, doc: dict) -> tuple[dict, bool]:
        try:
            result = await self._jobs.insert_one(doc)
        except DuplicateKeyError:
            existing = await self._jobs.find_one({"source": doc["source"], "source_job_id": doc["source_job_id"]})
            if existing is None:
                raise DuplicateError("Duplicate job could not be reloaded") from None
            return existing, False
        except PyMongoError as exc:
            raise_for_database(exc)
        doc["_id"] = result.inserted_id
        return doc, True

    async def list_jobs(self, *, min_score: float, skip: int, limit: int) -> tuple[list[dict], int]:
        query = {"match_score": {"$gte": min_score}}
        try:
            total = await self._jobs.count_documents(query)
            cursor = self._jobs.find(query).sort("created_at", -1).skip(skip).limit(limit)
            return await cursor.to_list(length=limit), total
        except PyMongoError as exc:
            raise_for_database(exc)

    async def get(self, job_id: str) -> dict | None:
        if not ObjectId.is_valid(job_id):
            return None
        try:
            return await self._jobs.find_one({"_id": ObjectId(job_id)})
        except PyMongoError as exc:
            raise_for_database(exc)
