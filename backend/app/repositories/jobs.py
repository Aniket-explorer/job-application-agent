from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.connectors.career_page.greenhouse import (
    board_digest,
    greenhouse_source_job_id,
    publishable_canonical_url,
    split_legacy_greenhouse_source_job_id,
    url_embeds_board_token,
)
from app.core.errors import DuplicateError, raise_for_database
from app.db.client import get_db

_DISCOVERED_UPDATE_FIELDS = (
    "source_job_id",
    "board_digest",
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


def _is_manual(doc: dict) -> bool:
    return doc.get("origin") == "manual" or doc.get("source") == "manual"


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

    async def migrate_legacy_greenhouse_ids(self) -> int:
        """Rewrite `greenhouse:{token}:{id}` in place. Does not insert a second job."""
        changed = 0
        skipped: set = set()
        query = {"source_job_id": {"$regex": r"^greenhouse:(?!sha256:[0-9a-f]{64}:)"}}
        while True:
            try:
                rows = await self._jobs.find(query).to_list(length=200)
            except PyMongoError as exc:
                raise_for_database(exc)
            pending = [row for row in rows if row["_id"] not in skipped]
            if not pending:
                return changed
            for row in pending:
                parsed = split_legacy_greenhouse_source_job_id(str(row.get("source_job_id", "")))
                if parsed is None:
                    skipped.add(row["_id"])
                    continue
                token, job_id = parsed
                new_id = greenhouse_source_job_id(token, job_id)
                try:
                    target = await self._jobs.find_one({"source": row.get("source"), "source_job_id": new_id})
                except PyMongoError as exc:
                    raise_for_database(exc)
                if target is not None and target["_id"] != row["_id"]:
                    if _is_manual(row) or await self._job_is_referenced(row["_id"]):
                        await self._drop_embedded_board_url(row, token)
                        skipped.add(row["_id"])
                        continue
                    try:
                        await self._jobs.delete_one({"_id": row["_id"]})
                    except PyMongoError as exc:
                        raise_for_database(exc)
                    changed += 1
                    continue
                url = row.get("canonical_url")
                published = publishable_canonical_url(url, token) if isinstance(url, str) else url
                updates = {"source_job_id": new_id, "board_digest": board_digest(token)}
                if published != url:
                    updates["canonical_url"] = published
                try:
                    await self._jobs.update_one({"_id": row["_id"]}, {"$set": updates, "$unset": {"board_token": ""}})
                except DuplicateKeyError:
                    if _is_manual(row) or await self._job_is_referenced(row["_id"]):
                        await self._drop_embedded_board_url(row, token)
                        skipped.add(row["_id"])
                        continue
                    try:
                        await self._jobs.delete_one({"_id": row["_id"]})
                    except PyMongoError as exc:
                        raise_for_database(exc)
                except PyMongoError as exc:
                    raise_for_database(exc)
                changed += 1

    async def _job_is_referenced(self, job_oid) -> bool:
        """Applications and match rows point at the job _id, which an in-place rename keeps."""
        job_id = str(job_oid)
        database = get_db()
        try:
            if await database.applications.count_documents({"job_id": job_id}, limit=1):
                return True
            return bool(await database.job_matches.count_documents({"job_id": job_id}, limit=1))
        except PyMongoError as exc:
            raise_for_database(exc)

    async def _drop_embedded_board_url(self, row: dict, token: str) -> None:
        url = row.get("canonical_url")
        if not isinstance(url, str) or not url_embeds_board_token(url, token):
            return
        try:
            await self._jobs.update_one(
                {"_id": row["_id"]},
                {"$set": {"canonical_url": None}, "$unset": {"board_token": ""}},
            )
        except PyMongoError as exc:
            raise_for_database(exc)

    async def upsert_discovered(self, doc: dict) -> tuple[dict, str]:
        """Insert a discovered job, or refresh an existing discovered row with the same source id.

        A manual import that already uses that source and source_job_id is returned unchanged.
        A legacy `greenhouse:{token}:{id}` row is reused instead of inserted again.
        """
        payload = dict(doc)
        legacy_id = payload.pop("_legacy_source_job_id", None)
        key = {"source": payload["source"], "source_job_id": payload["source_job_id"]}
        try:
            existing = await self._find_discovered_match(key, legacy_id)
        except PyMongoError as exc:
            raise_for_database(exc)
        if existing is not None:
            return await self._refresh_or_preserve(existing, payload)
        try:
            result = await self._jobs.insert_one(payload)
        except DuplicateKeyError:
            try:
                existing = await self._find_discovered_match(key, legacy_id)
            except PyMongoError as exc:
                raise_for_database(exc)
            if existing is None:
                raise DuplicateError("Duplicate job could not be reloaded") from None
            return await self._refresh_or_preserve(existing, payload)
        except PyMongoError as exc:
            raise_for_database(exc)
        payload["_id"] = result.inserted_id
        return payload, "created"

    async def _find_discovered_match(self, key: dict, legacy_id: str | None) -> dict | None:
        existing = await self._jobs.find_one(key)
        if existing is None and legacy_id:
            existing = await self._jobs.find_one({"source": key["source"], "source_job_id": legacy_id})
        return existing

    async def _refresh_or_preserve(self, existing: dict, doc: dict) -> tuple[dict, str]:
        manual = _is_manual(existing)
        if manual and existing.get("source_job_id") == doc["source_job_id"]:
            return existing, "preserved"
        changes = {} if manual else {field: doc[field] for field in _DISCOVERED_UPDATE_FIELDS if field in doc}
        if existing.get("source_job_id") != doc["source_job_id"]:
            changes["source_job_id"] = doc["source_job_id"]
        if "board_digest" in doc:
            changes["board_digest"] = doc["board_digest"]
        if not changes:
            return existing, "preserved"
        try:
            updated = await self._jobs.find_one_and_update(
                {"_id": existing["_id"]},
                {"$set": changes, "$unset": {"board_token": ""}},
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            if manual:
                return existing, "preserved"
            winner = await self._jobs.find_one({"source": doc["source"], "source_job_id": doc["source_job_id"]})
            if winner is None:
                raise DuplicateError("Duplicate job could not be reloaded") from None
            if existing["_id"] != winner["_id"]:
                await self._jobs.delete_one({"_id": existing["_id"]})
            return await self._refresh_or_preserve(winner, doc)
        except PyMongoError as exc:
            raise_for_database(exc)
        if updated is None:
            raise DuplicateError("Discovered job disappeared during update") from None
        return updated, "preserved" if manual else "updated"

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
