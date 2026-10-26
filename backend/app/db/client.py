import asyncio
import logging

from pymongo import AsyncMongoClient
from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: AsyncMongoClient | None = None
_client_loop_id: int | None = None
_redis: Redis | None = None
_redis_loop_id: int | None = None


def _loop_id() -> int:
    return id(asyncio.get_running_loop())


def get_client() -> AsyncMongoClient:
    """Return the Mongo client for the current event loop.

    AsyncMongoClient cannot move between loops. Uvicorn uses one loop, so this
    stays a single client in production. Tests get a fresh client when the loop changes.
    """
    global _client, _client_loop_id
    current = _loop_id()
    if _client is not None and _client_loop_id != current:
        _client = None
    if _client is None:
        _client = AsyncMongoClient(settings.mongodb_url, serverSelectionTimeoutMS=2500)
        _client_loop_id = current
    return _client


def get_db():
    return get_client()[settings.mongodb_database]


def get_redis() -> Redis:
    global _redis, _redis_loop_id
    current = _loop_id()
    if _redis is not None and _redis_loop_id != current:
        _redis = None
    if _redis is None:
        _redis = Redis.from_url(settings.redis_url, socket_connect_timeout=2)
        _redis_loop_id = current
    return _redis


async def close_db() -> None:
    global _client, _client_loop_id, _redis, _redis_loop_id
    client, _client, _client_loop_id = _client, None, None
    redis, _redis, _redis_loop_id = _redis, None, None
    if client is not None:
        try:
            await client.close()
        except RuntimeError:
            logger.warning("mongo client close skipped because its event loop was already closed")
    if redis is not None:
        try:
            await redis.aclose()
        except RuntimeError:
            logger.warning("redis client close skipped because its event loop was already closed")
