from fastapi import APIRouter, HTTPException

from app.api.serializers import serialize_application, serialize_job, serialize_job_detail
from app.core.errors import AppError, PolicyViolationError
from app.models import ApplicationCreate, AutomationSettings, JobImport
from app.services.applications import ApplicationService
from app.services.jobs import JobService
from app.services.settings import SettingsService
from app.services.sources import list_sources

router = APIRouter()
_jobs = JobService()
_applications = ApplicationService()
_settings = SettingsService()


def _http(exc: AppError) -> HTTPException:
    # Preserve the starter's 400 for rejected live mode. New clients use /api/v1 and receive 422.
    status = 400 if isinstance(exc, PolicyViolationError) else exc.http_status
    return HTTPException(status_code=status, detail=exc.message)


@router.get("/api/connectors")
async def connector_statuses():
    return list_sources()


@router.post("/api/jobs/import")
async def import_job(payload: JobImport):
    try:
        doc, _created = await _jobs.import_job(payload)
    except AppError as exc:
        raise _http(exc) from exc
    return serialize_job(doc)


@router.get("/api/jobs")
async def list_jobs(limit: int = 50, min_score: int = 0):
    limit = max(1, min(limit, 200))
    try:
        docs, _total = await _jobs.list_jobs(min_score=min_score, skip=0, limit=limit)
    except AppError as exc:
        raise _http(exc) from exc
    return [serialize_job(doc) for doc in docs]


@router.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    try:
        doc = await _jobs.get_job(job_id)
    except AppError as exc:
        raise _http(exc) from exc
    if doc is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return serialize_job_detail(doc)


@router.post("/api/applications")
async def create_application(payload: ApplicationCreate):
    try:
        prepared = await _applications.prepare(payload.job_id, payload.candidate_id)
    except AppError as exc:
        raise _http(exc) from exc
    return serialize_application(prepared.document, duplicate=not prepared.created)


@router.get("/api/applications")
async def list_applications(limit: int = 100):
    limit = max(1, min(limit, 200))
    try:
        docs, _total = await _applications.list_applications(skip=0, limit=limit)
    except AppError as exc:
        raise _http(exc) from exc
    return [serialize_application(doc) for doc in docs]


@router.get("/api/settings")
async def get_settings():
    try:
        current = await _settings.get()
    except AppError as exc:
        raise _http(exc) from exc
    return current.model_dump()


@router.put("/api/settings")
async def update_settings(payload: AutomationSettings):
    try:
        current = await _settings.update(payload)
    except AppError as exc:
        raise _http(exc) from exc
    return current.model_dump()
