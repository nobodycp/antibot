"""
Best-effort Django cache operations: never raise for performance / optional paths.

When the configured backend (e.g. Redis) is down or misconfigured, callers should
degrade gracefully instead of failing the request.
"""

from __future__ import annotations

import logging
from typing import Any, TypeVar

from django.core.cache import cache

logger = logging.getLogger(__name__)

T = TypeVar("T")


def safe_cache_get(key: str, default: T | None = None) -> T | None:
    try:
        return cache.get(key, default)
    except Exception:
        logger.debug("cache.get failed for key %r", key, exc_info=True)
        return default


def safe_cache_set(key: str, value: Any, timeout: int | None) -> bool:
    try:
        cache.set(key, value, timeout)
        return True
    except Exception:
        logger.debug("cache.set failed for key %r", key, exc_info=True)
        return False


def safe_cache_delete(key: str) -> bool:
    try:
        cache.delete(key)
        return True
    except Exception:
        logger.debug("cache.delete failed for key %r", key, exc_info=True)
        return False


def safe_cache_add(key: str, value: Any, timeout: int | None) -> bool:
    try:
        return bool(cache.add(key, value, timeout))
    except Exception:
        logger.debug("cache.add failed for key %r", key, exc_info=True)
        return False


def safe_cache_incr(key: str, delta: int = 1) -> int | None:
    """
    Increment counter; return None if backend error (not missing key).

    Missing keys still raise ValueError so callers can initialize with add().
    """
    try:
        return cache.incr(key, delta)
    except ValueError:
        raise
    except Exception:
        logger.debug("cache.incr failed for key %r", key, exc_info=True)
        return None
