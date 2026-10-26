from pymongo.errors import PyMongoError

from app.core.errors import raise_for_database
from app.db.client import get_db
from app.scoring.engine import MATCHING_VERSION


class MatchRepository:
    @property
    def _matches(self):
        return get_db().job_matches

    async def upsert(self, doc: dict) -> dict:
        key = {
            "candidate_id": doc["candidate_id"],
            "job_id": doc["job_id"],
            "matching_version": doc["matching_version"],
        }
        try:
            await self._matches.replace_one(key, doc, upsert=True)
            stored = await self._matches.find_one(key)
        except PyMongoError as exc:
            raise_for_database(exc)
        return stored or doc

    async def get(self, job_id: str, candidate_id: str = "default-candidate") -> dict | None:
        try:
            return await self._matches.find_one(
                {"job_id": job_id, "candidate_id": candidate_id, "matching_version": MATCHING_VERSION}
            )
        except PyMongoError as exc:
            raise_for_database(exc)

    async def ids_at_or_above(self, minimum: float, candidate_id: str = "default-candidate") -> list[str]:
        try:
            cursor = self._matches.find(
                {
                    "candidate_id": candidate_id,
                    "matching_version": MATCHING_VERSION,
                    "total_score": {"$gte": minimum},
                },
                {"job_id": 1},
            )
            rows = await cursor.to_list(length=1000)
        except PyMongoError as exc:
            raise_for_database(exc)
        return [row["job_id"] for row in rows if isinstance(row.get("job_id"), str)]

    async def for_jobs(self, job_ids: list[str], candidate_id: str = "default-candidate") -> dict[str, dict]:
        if not job_ids:
            return {}
        try:
            cursor = self._matches.find(
                {"job_id": {"$in": job_ids}, "candidate_id": candidate_id, "matching_version": MATCHING_VERSION}
            )
            rows = await cursor.to_list(length=len(job_ids))
        except PyMongoError as exc:
            raise_for_database(exc)
        return {row["job_id"]: row for row in rows}
