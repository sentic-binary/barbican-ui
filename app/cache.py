"""Barbican UI – Disk-based cache using diskcache."""

from __future__ import annotations

import json
import logging
import zlib

import diskcache

from app.config import Config

logger = logging.getLogger(__name__)

_cache: diskcache.Cache | None = None


class _JSONDisk(diskcache.Disk):
    """Custom disk serializer using JSON instead of pickle to avoid
    arbitrary code execution via CVE-2025-69872."""

    def store(self, value, read, key=diskcache.UNKNOWN):
        if not read:
            value = zlib.compress(json.dumps(value).encode("utf-8"))
        return super().store(value, read, key=key)

    def fetch(self, mode, filename, value, read):
        data = super().fetch(mode, filename, value, read)
        if not read and isinstance(data, bytes):
            data = json.loads(zlib.decompress(data).decode("utf-8"))
        return data


def get_cache() -> diskcache.Cache:
    global _cache
    if _cache is None:
        _cache = diskcache.Cache(
            Config.CACHE_DIR,
            eviction_policy="least-recently-used",
            disk=_JSONDisk,
        )
        logger.info("Cache initialised at %s", Config.CACHE_DIR)
    return _cache
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

