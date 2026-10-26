import hashlib
import json

from app.core.errors import NotFoundError
from app.models import utcnow
from app.repositories.jobs import JobRepository
from app.repositories.matches import MatchRepository
from app.scoring.engine import MATCHING_VERSION, score_job
from app.scoring.profile import load_profile, profile_fingerprint
from app.services.settings import SettingsService


class ScoringService:
    """Persist explainable scores. This service does not read or write applications."""

    def __init__(self, jobs: JobRepository | None = None, matches: MatchRepository | None = None, settings: SettingsService | None = None):
        self._jobs = jobs or JobRepository()
        self._matches = matches or MatchRepository()
        self._settings = settings or SettingsService()

    async def score_job(self, job_id: str) -> dict:
        job = await self._jobs.get(job_id)
        if job is None:
            raise NotFoundError("Job not found")
        return await self._score_document(job)

    async def score_all(self) -> dict:
        jobs = await self._jobs.find_all()
        scored = []
        for job in jobs:
            scored.append(await self._score_document(job))
        return {"scored": len(scored), "items": scored}

    async def stored_for(self, job_ids: list[str]) -> dict[str, dict]:
        rows = await self._matches.for_jobs(job_ids)
        threshold = (await self._settings.get()).minimum_match_score
        return {job_id: present_match(row, threshold) for job_id, row in rows.items()}

    async def _score_document(self, job: dict) -> dict:
        threshold = (await self._settings.get()).minimum_match_score
        profile, resume_text, notes = load_profile()
        assessment = score_job(job, profile, threshold=threshold, resume_text=resume_text, warnings=notes)
        content_hash = hashlib.sha256(
            json.dumps(
                {
                    "title": job.get("title"),
                    "description": job.get("description"),
                    "location": job.get("location"),
                    "remote_type": job.get("remote_type"),
                },
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        doc = assessment.model_dump()
        doc.update(
            {
                "job_id": str(job["_id"]),
                "content_hash": content_hash,
                "profile_fingerprint": profile_fingerprint(profile, resume_text),
                "evaluated_at": utcnow(),
                "matching_version": MATCHING_VERSION,
            }
        )
        stored = await self._matches.upsert(doc)
        return present_match(stored, threshold)


def present_match(doc: dict, threshold: float) -> dict:
    total = doc.get("total_score")
    body = {
        "candidate_id": doc.get("candidate_id", "default-candidate"),
        "matching_version": doc.get("matching_version", MATCHING_VERSION),
        "total_score": total,
        "threshold": threshold,
        "meets_threshold": total is not None and total >= threshold,
        "match_status": doc.get("match_status", "insufficient_information"),
        "factors": doc.get("factors", []),
        "matched_skills": doc.get("matched_skills", []),
        "missing_skills": doc.get("missing_skills", []),
        "warnings": doc.get("warnings", []),
        "weight_used": doc.get("weight_used", 0),
        "weight_excluded": doc.get("weight_excluded", 0),
        "evaluated_at": doc.get("evaluated_at"),
    }
    return body
