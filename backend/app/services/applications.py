from dataclasses import dataclass

from app.core.errors import BelowThresholdError, NotFoundError
from app.models import utcnow
from app.repositories.applications import ApplicationRepository
from app.repositories.audit import AuditRepository
from app.repositories.jobs import JobRepository
from app.services.settings import SettingsService


@dataclass
class PreparedApplication:
    document: dict
    created: bool


class ApplicationService:
    def __init__(
        self,
        jobs: JobRepository | None = None,
        applications: ApplicationRepository | None = None,
        settings: SettingsService | None = None,
        audit: AuditRepository | None = None,
    ) -> None:
        self._jobs = jobs or JobRepository()
        self._applications = applications or ApplicationRepository()
        self._settings = settings or SettingsService()
        self._audit = audit or AuditRepository()

    async def prepare(self, job_id: str, candidate_id: str) -> PreparedApplication:
        job = await self._jobs.get(job_id)
        if job is None:
            raise NotFoundError("Job not found")
        policy = await self._settings.get()
        score = float(job.get("match_score") or 0)
        if score < policy.minimum_match_score:
            raise BelowThresholdError(f"Match score {score} is below threshold {policy.minimum_match_score}")
        now = utcnow()
        doc = {
            "job_id": job_id,
            "candidate_id": candidate_id,
            "channel": job["source"],
            "status": "dry_run",
            "match_score": score,
            "dry_run": True,
            "created_at": now,
            "updated_at": now,
            "submitted_at": None,
            "error": None,
        }
        stored, created = await self._applications.insert_or_get_existing(doc)
        if created:
            await self._audit.record(
                entity_id=str(stored["_id"]),
                event="application_dry_run_created",
                details={"job_id": job_id, "score": score},
            )
        return PreparedApplication(document=stored, created=created)

    async def list_applications(self, *, skip: int, limit: int) -> tuple[list[dict], int]:
        return await self._applications.list_applications(skip=skip, limit=limit)

    async def get_application(self, application_id: str) -> dict:
        doc = await self._applications.get(application_id)
        if doc is None:
            raise NotFoundError("Application not found")
        return doc
