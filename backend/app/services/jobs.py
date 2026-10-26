from app.matching import calculate_match_score
from app.models import JobImport, utcnow
from app.repositories.jobs import JobRepository
from app.repositories.matches import MatchRepository


class JobService:
    def __init__(self, jobs: JobRepository | None = None, matches: MatchRepository | None = None) -> None:
        self._jobs = jobs or JobRepository()
        self._matches = matches or MatchRepository()

    async def import_job(self, payload: JobImport) -> tuple[dict, bool]:
        now = utcnow()
        score = calculate_match_score(payload.description)
        doc = payload.model_dump(mode="json")
        doc.update(
            {
                "canonical_url": str(payload.canonical_url),
                "match_score": score["score"],
                "match_factors": score["factors"],
                "match_reasons": score["reasons"],
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
        )
        return await self._jobs.insert_or_get_existing(doc)

    async def list_jobs(self, *, min_score: float, skip: int, limit: int, origin: str | None = None) -> tuple[list[dict], int]:
        allowed_ids = None
        if min_score > 0:
            allowed_ids = await self._matches.ids_at_or_above(min_score)
        return await self._jobs.list_jobs(
            min_score=min_score,
            skip=skip,
            limit=limit,
            origin=origin,
            allowed_ids=allowed_ids,
        )

    async def get_job(self, job_id: str) -> dict | None:
        return await self._jobs.get(job_id)
