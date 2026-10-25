from datetime import datetime, timezone
from app.worker import celery_app
from app.config import settings

@celery_app.task(name="app.tasks.hourly_scan")
def hourly_scan() -> dict:
    """Safe scheduler placeholder: no live source calls until connectors are explicitly implemented."""
    return {"status": "dry_run", "message": "No source connectors are configured; no external requests were made.", "checked_at": datetime.now(timezone.utc).isoformat(), "dry_run": settings.dry_run}

@celery_app.task(name="app.tasks.prepare_application")
def prepare_application(application_id: str) -> dict:
    """Placeholder task. Real submission must re-check policy, source capability, and idempotency."""
    return {"application_id": application_id, "status": "dry_run", "submitted": False, "reason": "Live application connector not implemented."}
