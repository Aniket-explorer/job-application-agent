from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

_client: AsyncIOMotorClient | None = None

def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongodb_url, serverSelectionTimeoutMS=2500)
    return _client

def get_db():
    return get_client()[settings.mongodb_database]

async def close_db() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None

async def ensure_indexes() -> None:
    db = get_db()
    await db.jobs.create_index([("source", 1), ("source_job_id", 1)], unique=True, sparse=True)
    await db.jobs.create_index("canonical_url")
    await db.jobs.create_index("created_at")
    await db.applications.create_index([("candidate_id", 1), ("job_id", 1)], unique=True)
    await db.applications.create_index([("status", 1), ("created_at", -1)])
    await db.audit_events.create_index([("entity_id", 1), ("created_at", -1)])
