from fastapi import APIRouter

from app.api.v1.routes import applications, health, jobs, settings, sources

router = APIRouter(prefix="/api/v1")
router.include_router(health.router)
router.include_router(jobs.router)
router.include_router(applications.router)
router.include_router(settings.router)
router.include_router(sources.router)
