from typing import Literal

from fastapi import APIRouter, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.serializers import page, serialize_application, serialize_job, serialize_job_detail
from app.core.errors import DuplicateError, NotFoundError
from app.models import JobImport, PrepareApplication
from app.services.applications import ApplicationService
from app.services.jobs import JobService
from app.services.scoring import ScoringService

router = APIRouter(prefix="/jobs", tags=["jobs"])
_jobs = JobService()
_applications = ApplicationService()
_scoring = ScoringService()


@router.get("")
async def list_jobs(
    page_number: int = Query(1, alias="page", ge=1),
    page_size: int = Query(25, ge=1, le=100),
    min_score: float = Query(0, ge=0, le=100),
    origin: Literal["manual", "discovered"] | None = None,
):
    docs, total = await _jobs.list_jobs(
        min_score=min_score,
        skip=(page_number - 1) * page_size,
        limit=page_size,
        origin=origin,
    )
    assessments = await _scoring.stored_for([str(doc["_id"]) for doc in docs])
    items = [serialize_job(doc, assessments.get(str(doc["_id"]))) for doc in docs]
    return page(items, total=total, page_number=page_number, page_size=page_size)


@router.post("/score")
async def score_jobs():
    return await _scoring.score_all()


@router.get("/{job_id}")
async def get_job(job_id: str):
    doc = await _jobs.get_job(job_id)
    if doc is None:
        raise NotFoundError("Job not found")
    assessments = await _scoring.stored_for([job_id])
    return serialize_job_detail(doc, assessments.get(job_id))


@router.post("/{job_id}/score")
async def score_job(job_id: str):
    return await _scoring.score_job(job_id)


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
