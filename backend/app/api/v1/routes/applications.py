from fastapi import APIRouter, Query

from app.api.serializers import page, serialize_application
from app.services.applications import ApplicationService

router = APIRouter(prefix="/applications", tags=["applications"])
_applications = ApplicationService()


@router.get("")
async def list_applications(
    page_number: int = Query(1, alias="page", ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    docs, total = await _applications.list_applications(skip=(page_number - 1) * page_size, limit=page_size)
    return page([serialize_application(doc) for doc in docs], total=total, page_number=page_number, page_size=page_size)


@router.get("/{application_id}")
async def get_application(application_id: str):
    doc = await _applications.get_application(application_id)
    return serialize_application(doc)
