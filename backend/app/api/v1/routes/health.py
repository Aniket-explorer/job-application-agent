from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from app.db.client import get_db, get_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/ready")
async def ready():
    checks = {"mongodb": "unavailable", "redis": "unavailable"}
    try:
        await get_db().command("ping")
        checks["mongodb"] = "ok"
    except PyMongoError:
        checks["mongodb"] = "unavailable"
    try:
        await get_redis().ping()
        checks["redis"] = "ok"
    except (RedisError, OSError):
        checks["redis"] = "unavailable"
    ready_ok = all(value == "ok" for value in checks.values())
    return JSONResponse(
        status_code=200 if ready_ok else 503,
        content={"status": "ready" if ready_ok else "not_ready", "checks": checks},
    )
