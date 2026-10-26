"""Compatibility import. New code should use app.core.config."""

from app.core.config import Settings, settings

__all__ = ["Settings", "settings"]
