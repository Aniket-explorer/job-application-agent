from app.db.client import get_db

SETTINGS_ID = "global"


async def ensure_indexes() -> None:
    db = get_db()
    await db.jobs.create_index([("source", 1), ("source_job_id", 1)], unique=True, sparse=True)
    await db.jobs.create_index("canonical_url")
    await db.jobs.create_index("created_at")
    await db.applications.create_index([("candidate_id", 1), ("job_id", 1)], unique=True)
    await db.applications.create_index([("status", 1), ("created_at", -1)])
    await db.audit_events.create_index([("entity_id", 1), ("created_at", -1)])
    await db.audit_events.create_index("created_at")
