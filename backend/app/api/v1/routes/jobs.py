from fastapi import APIRouter, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.serializers import page, serialize_application, serialize_job, serialize_job_detail
from app.core.errors import DuplicateError, NotFoundError
from app.models import JobImport, PrepareApplication
from app.services.applications import ApplicationService
from app.services.jobs import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])
_jobs = JobService()
_applications = ApplicationService()


@router.get("")
async def list_jobs(
    page_number: int = Query(1, alias="page", ge=1),
    page_size: int = Query(25, ge=1, le=100),
    min_score: float = Query(0, ge=0, le=100),
):
    docs, total = await _jobs.list_jobs(min_score=min_score, skip=(page_number - 1) * page_size, limit=page_size)
    return page([serialize_job(doc) for doc in docs], total=total, page_number=page_number, page_size=page_size)


@router.get("/{job_id}")
async def get_job(job_id: str):
    doc = await _jobs.get_job(job_id)
    if doc is None:
        raise NotFoundError("Job not found")
    return serialize_job_detail(doc)


@router.post("/import")
async def import_job(payload: JobImport):
    doc, created = await _jobs.import_job(payload)
    body = serialize_job(doc)
    body["created"] = created
    return JSONResponse(status_code=201 if created else 200, content=jsonable_encoder(body))


@router.post("/{job_id}/prepare-application", status_code=201)
async def prepare_application(job_id: str, payload: PrepareApplication | None = None):
    candidate_id = payload.candidate_id if payload else "default-candidate"
    prepared = await _applications.prepare(job_id, candidate_id)
    body = serialize_application(prepared.document)
    if not prepared.created:
        raise DuplicateError("An application already exists for this job", {"application_id": body["id"]})
    return body
