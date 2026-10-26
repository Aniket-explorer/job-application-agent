"""Compatibility import. New code should use app.db.client and app.db.indexes."""

from app.db.client import close_db, get_client, get_db, get_redis
from app.db.indexes import ensure_indexes

__all__ = ["close_db", "ensure_indexes", "get_client", "get_db", "get_redis"]
