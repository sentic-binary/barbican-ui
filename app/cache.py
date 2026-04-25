"""Barbican UI – Disk-based cache using diskcache."""

from __future__ import annotations

import logging

import diskcache

from app.config import Config

logger = logging.getLogger(__name__)

_cache: diskcache.Cache | None = None


def get_cache() -> diskcache.Cache:
    global _cache
    if _cache is None:
        _cache = diskcache.Cache(Config.CACHE_DIR, eviction_policy="least-recently-used")
        logger.info("Cache initialised at %s", Config.CACHE_DIR)
    return _cache


def cache_get(key: str):
    """Return cached value or None."""
    return get_cache().get(key)


def cache_set(key: str, value, ttl: int | None = None):
    """Store value with TTL (defaults to Config.CACHE_TTL_SECONDS)."""
    if ttl is None:
        ttl = Config.CACHE_TTL_SECONDS
    get_cache().set(key, value, expire=ttl)


def cache_delete(key: str):
    """Delete a specific cache entry."""
    try:
        del get_cache()[key]
    except KeyError:
        pass


def cache_invalidate_prefix(prefix: str):
    """Delete all cache entries whose key starts with prefix."""
    c = get_cache()
    keys_to_delete = [k for k in c if isinstance(k, str) and k.startswith(prefix)]
    for k in keys_to_delete:
        try:
            del c[k]
        except KeyError:
            pass

