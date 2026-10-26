from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.errors import DuplicateError, raise_for_database
from app.db.client import get_db

_DISCOVERED_UPDATE_FIELDS = (
    "company",
    "company_normalized",
    "title",
    "title_normalized",
    "description",
    "location",
    "location_normalized",
    "canonical_url",
    "posted_at",
    "content_hash",
    "last_seen_at",
    "updated_at",
    "status",
    "provider",
)


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

    async def upsert_discovered(self, doc: dict) -> tuple[dict, str]:
        """Insert a discovered job, or refresh an existing discovered row with the same source id.

        A manual import that already uses that source and source_job_id is returned unchanged.
        """
        key = {"source": doc["source"], "source_job_id": doc["source_job_id"]}
        try:
            existing = await self._jobs.find_one(key)
        except PyMongoError as exc:
            raise_for_database(exc)
        if existing is not None:
            return await self._refresh_or_preserve(existing, doc)
        try:
            result = await self._jobs.insert_one(doc)
        except DuplicateKeyError:
            existing = await self._jobs.find_one(key)
            if existing is None:
                raise DuplicateError("Duplicate job could not be reloaded") from None
            return await self._refresh_or_preserve(existing, doc)
        except PyMongoError as exc:
            raise_for_database(exc)
        doc["_id"] = result.inserted_id
        return doc, "created"

    async def _refresh_or_preserve(self, existing: dict, doc: dict) -> tuple[dict, str]:
        if existing.get("origin") == "manual" or existing.get("source") == "manual":
            return existing, "preserved"
        changes = {field: doc[field] for field in _DISCOVERED_UPDATE_FIELDS if field in doc}
        try:
            updated = await self._jobs.find_one_and_update(
                {"_id": existing["_id"]},
                {"$set": changes},
                return_document=ReturnDocument.AFTER,
            )
        except PyMongoError as exc:
            raise_for_database(exc)
        if updated is None:
            raise DuplicateError("Discovered job disappeared during update") from None
        return updated, "updated"

    async def find_all(self, limit: int = 500) -> list[dict]:
        try:
            return await self._jobs.find({}).limit(limit).to_list(length=limit)
        except PyMongoError as exc:
            raise_for_database(exc)

    async def list_jobs(
        self,
        *,
        min_score: float,
        skip: int,
        limit: int,
        origin: str | None = None,
        allowed_ids: list[str] | None = None,
    ) -> tuple[list[dict], int]:
        clauses: list[dict] = []
        if origin == "discovered":
            clauses.append({"origin": "discovered"})
        elif origin == "manual":
            clauses.append({"$or": [{"origin": "manual"}, {"source": "manual", "origin": {"$exists": False}}]})
        if min_score > 0:
            identifiers = [ObjectId(value) for value in (allowed_ids or []) if ObjectId.is_valid(value)]
            clauses.append({"_id": {"$in": identifiers}})
        query: dict = {"$and": clauses} if len(clauses) > 1 else (clauses[0] if clauses else {})
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
