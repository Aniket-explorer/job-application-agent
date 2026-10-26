from app.matching import calculate_match_score
from app.models import JobImport, utcnow
from app.repositories.jobs import JobRepository


class JobService:
    def __init__(self, jobs: JobRepository | None = None) -> None:
        self._jobs = jobs or JobRepository()

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

    async def list_jobs(self, *, min_score: float, skip: int, limit: int) -> tuple[list[dict], int]:
        return await self._jobs.list_jobs(min_score=min_score, skip=skip, limit=limit)

    async def get_job(self, job_id: str) -> dict | None:
        return await self._jobs.get(job_id)
