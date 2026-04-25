"""Barbican UI – Barbican API client.

Covers all 15 CLI-equivalent operations:
  Secrets:    store, list, get, delete, update
  Containers: create, list, get, delete
  Consumers:  create, list, delete
  Orders:     create, list, get, delete

Required OpenStack permissions:
  - Keystone: POST /v3/auth/tokens (any valid user)
  - Barbican: project-scoped token with 'creator' role on the key-manager
    service.  No admin or other service permissions needed.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from app.cache import cache_delete, cache_get, cache_invalidate_prefix, cache_set

logger = logging.getLogger(__name__)

_TIMEOUT = 30


class BarbicanError(Exception):
    """Raised on Barbican API errors."""

    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


def _headers(token: str, content_type: str = "application/json") -> dict[str, str]:
    h = {"X-Auth-Token": token}
    if content_type:
        h["Content-Type"] = content_type
    return h


def _url(endpoint: str, path: str) -> str:
    return f"{endpoint.rstrip('/')}/{path.lstrip('/')}"


def _check(resp: requests.Response, expected: tuple[int, ...] = (200, 201, 204)):
    if resp.status_code not in expected:
        detail = ""
        try:
            detail = resp.json().get("title", resp.text[:300])
        except Exception:
            detail = resp.text[:300]
        raise BarbicanError(
            f"Barbican API error {resp.status_code}: {detail}",
            status_code=resp.status_code,
        )


def _cache_key(project_id: str, resource: str) -> str:
    return f"{project_id}:{resource}"


# ── Secrets ─────────────────────────────────────────────────────────────────

def secret_store(
    endpoint: str,
    token: str,
    project_id: str,
    *,
    name: str = "",
    payload: str = "",
    payload_content_type: str = "text/plain",
    payload_content_encoding: str = "",
    secret_type: str = "opaque",
    algorithm: str = "",
    bit_length: int = 0,
    mode: str = "",
    expiration: str = "",
) -> dict[str, Any]:
    """POST /v1/secrets — store a new secret."""
    body: dict[str, Any] = {"secret_type": secret_type}
    if name:
        body["name"] = name
    if payload:
        body["payload"] = payload
        body["payload_content_type"] = payload_content_type
        if payload_content_encoding:
            body["payload_content_encoding"] = payload_content_encoding
    if algorithm:
        body["algorithm"] = algorithm
    if bit_length:
        body["bit_length"] = bit_length
    if mode:
        body["mode"] = mode
    if expiration:
        body["expiration"] = expiration

    resp = requests.post(
        _url(endpoint, "v1/secrets"),
        json=body,
        headers=_headers(token),
        timeout=_TIMEOUT,
    )
    _check(resp, (200, 201))
    cache_invalidate_prefix(_cache_key(project_id, "secrets"))
    return resp.json()


def secret_list(
    endpoint: str,
    token: str,
    project_id: str,
    *,
    limit: int = 100,
    offset: int = 0,
    name: str = "",
    sort: str = "created:desc",
) -> dict[str, Any]:
    """GET /v1/secrets — list secrets."""
    ck = _cache_key(project_id, f"secrets:list:{limit}:{offset}:{name}:{sort}")
    cached = cache_get(ck)
    if cached is not None:
        return cached

    params: dict[str, Any] = {"limit": limit, "offset": offset, "sort": sort}
    if name:
        params["name"] = name

    resp = requests.get(
        _url(endpoint, "v1/secrets"),
        params=params,
        headers=_headers(token),
        timeout=_TIMEOUT,
    )
    _check(resp)
    data = resp.json()
    cache_set(ck, data)
    return data


def secret_get(
    endpoint: str,
    token: str,
    project_id: str,
    secret_id: str,
) -> dict[str, Any]:
    """GET /v1/secrets/{id} — get secret metadata."""
    ck = _cache_key(project_id, f"secrets:{secret_id}:meta")
    cached = cache_get(ck)
    if cached is not None:
        return cached

    resp = requests.get(
        _url(endpoint, f"v1/secrets/{secret_id}"),
        headers=_headers(token),
        timeout=_TIMEOUT,
    )
    _check(resp)
    data = resp.json()
    cache_set(ck, data)
    return data


def secret_get_payload(
    endpoint: str,
    token: str,
    project_id: str,
    secret_id: str,
    accept: str = "text/plain",
) -> str:
    """GET /v1/secrets/{id}/payload — get secret payload.

    NOTE: Payloads are intentionally NOT cached to avoid storing
    sensitive plaintext data on disk.
    """
    resp = requests.get(
        _url(endpoint, f"v1/secrets/{secret_id}/payload"),
        headers={"X-Auth-Token": token, "Accept": accept},
        timeout=_TIMEOUT,
    )
    _check(resp)
    return resp.text


def secret_delete(
    endpoint: str,
    token: str,
    project_id: str,
    secret_id: str,
) -> None:
    """DELETE /v1/secrets/{id}"""
    resp = requests.delete(
        _url(endpoint, f"v1/secrets/{secret_id}"),
        headers=_headers(token),
        timeout=_TIMEOUT,
    )
    _check(resp, (200, 204))
    cache_invalidate_prefix(_cache_key(project_id, "secrets"))


def secret_update(
    endpoint: str,
    token: str,
    project_id: str,
    secret_id: str,
    payload: str,
    payload_content_type: str = "text/plain",
    payload_content_encoding: str = "",
) -> None:
    """PUT /v1/secrets/{id} — update (set) secret payload."""
    hdrs: dict[str, str] = {
        "X-Auth-Token": token,
        "Content-Type": payload_content_type,
    }
    if payload_content_encoding:
        hdrs["Content-Encoding"] = payload_content_encoding

    resp = requests.put(
        _url(endpoint, f"v1/secrets/{secret_id}"),
        data=payload.encode("utf-8") if isinstance(payload, str) else payload,
        headers=hdrs,
        timeout=_TIMEOUT,
    )
    _check(resp, (200, 204))
    cache_invalidate_prefix(_cache_key(project_id, f"secrets:{secret_id}"))
    cache_invalidate_prefix(_cache_key(project_id, "secrets:list"))


# ── Containers ──────────────────────────────────────────────────────────────

def container_create(
    endpoint: str,
    token: str,
    project_id: str,
    *,
    name: str,
    container_type: str = "generic",
    secret_refs: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """POST /v1/containers"""
    body: dict[str, Any] = {
        "name": name,
        "type": container_type,
        "secret_refs": secret_refs or [],
    }
    resp = requests.post(
        _url(endpoint, "v1/containers"),
        json=body,
        headers=_headers(token),
        timeout=_TIMEOUT,
    )
    _check(resp, (200, 201))
    cache_invalidate_prefix(_cache_key(project_id, "containers"))
    return resp.json()


def container_list(
    endpoint: str,
    token: str,
    project_id: str,
    *,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """GET /v1/containers"""
    ck = _cache_key(project_id, f"containers:list:{limit}:{offset}")
    cached = cache_get(ck)
    if cached is not None:
        return cached

    resp = requests.get(
        _url(endpoint, "v1/containers"),
        params={"limit": limit, "offset": offset},
        headers=_headers(token),
        timeout=_TIMEOUT,
    )
    _check(resp)
    data = resp.json()
    cache_set(ck, data)
    return data


def container_get(
    endpoint: str,
    token: str,
    project_id: str,
    container_id: str,
) -> dict[str, Any]:
    """GET /v1/containers/{id}"""
    ck = _cache_key(project_id, f"containers:{container_id}")
    cached = cache_get(ck)
    if cached is not None:
        return cached

    resp = requests.get(
        _url(endpoint, f"v1/containers/{container_id}"),
        headers=_headers(token),
        timeout=_TIMEOUT,
    )
    _check(resp)
    data = resp.json()
    cache_set(ck, data)
    return data


def container_delete(
    endpoint: str,
    token: str,
    project_id: str,
    container_id: str,
) -> None:
    """DELETE /v1/containers/{id}"""
    resp = requests.delete(
        _url(endpoint, f"v1/containers/{container_id}"),
        headers=_headers(token),
        timeout=_TIMEOUT,
    )
    _check(resp, (200, 204))
    cache_invalidate_prefix(_cache_key(project_id, "containers"))


# ── Consumers ───────────────────────────────────────────────────────────────

def consumer_create(
    endpoint: str,
    token: str,
    project_id: str,
    container_id: str,
    *,
    name: str,
    url: str,
) -> dict[str, Any]:
    """POST /v1/containers/{id}/consumers"""
    body = {"name": name, "URL": url}
    resp = requests.post(
        _url(endpoint, f"v1/containers/{container_id}/consumers"),
        json=body,
        headers=_headers(token),
        timeout=_TIMEOUT,
    )
    _check(resp, (200, 201))
    cache_invalidate_prefix(_cache_key(project_id, f"containers:{container_id}"))
    return resp.json()


def consumer_list(
    endpoint: str,
    token: str,
    project_id: str,
    container_id: str,
    *,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """GET /v1/containers/{id}/consumers"""
    ck = _cache_key(project_id, f"containers:{container_id}:consumers:{limit}:{offset}")
    cached = cache_get(ck)
    if cached is not None:
        return cached

    resp = requests.get(
        _url(endpoint, f"v1/containers/{container_id}/consumers"),
        params={"limit": limit, "offset": offset},
        headers=_headers(token),
        timeout=_TIMEOUT,
    )
    _check(resp)
    data = resp.json()
    cache_set(ck, data)
    return data


def consumer_delete(
    endpoint: str,
    token: str,
    project_id: str,
    container_id: str,
    *,
    name: str,
    url: str,
) -> None:
    """DELETE /v1/containers/{id}/consumers"""
    body = {"name": name, "URL": url}
    resp = requests.delete(
        _url(endpoint, f"v1/containers/{container_id}/consumers"),
        json=body,
        headers=_headers(token),
        timeout=_TIMEOUT,
    )
    _check(resp, (200, 204))
    cache_invalidate_prefix(_cache_key(project_id, f"containers:{container_id}"))


# ── Orders ──────────────────────────────────────────────────────────────────

def order_create(
    endpoint: str,
    token: str,
    project_id: str,
    *,
    order_type: str = "key",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST /v1/orders"""
    body: dict[str, Any] = {"type": order_type, "meta": meta or {}}
    resp = requests.post(
        _url(endpoint, "v1/orders"),
        json=body,
        headers=_headers(token),
        timeout=_TIMEOUT,
    )
    _check(resp, (200, 201, 202))
    cache_invalidate_prefix(_cache_key(project_id, "orders"))
    return resp.json()


def order_list(
    endpoint: str,
    token: str,
    project_id: str,
    *,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """GET /v1/orders"""
    ck = _cache_key(project_id, f"orders:list:{limit}:{offset}")
    cached = cache_get(ck)
    if cached is not None:
        return cached

    resp = requests.get(
        _url(endpoint, "v1/orders"),
        params={"limit": limit, "offset": offset},
        headers=_headers(token),
        timeout=_TIMEOUT,
    )
    _check(resp)
    data = resp.json()
    cache_set(ck, data)
    return data


def order_get(
    endpoint: str,
    token: str,
    project_id: str,
    order_id: str,
) -> dict[str, Any]:
    """GET /v1/orders/{id}"""
    ck = _cache_key(project_id, f"orders:{order_id}")
    cached = cache_get(ck)
    if cached is not None:
        return cached

    resp = requests.get(
        _url(endpoint, f"v1/orders/{order_id}"),
        headers=_headers(token),
        timeout=_TIMEOUT,
    )
    _check(resp)
    data = resp.json()
    cache_set(ck, data)
    return data


def order_delete(
    endpoint: str,
    token: str,
    project_id: str,
    order_id: str,
) -> None:
    """DELETE /v1/orders/{id}"""
    resp = requests.delete(
        _url(endpoint, f"v1/orders/{order_id}"),
        headers=_headers(token),
        timeout=_TIMEOUT,
    )
    _check(resp, (200, 204))
    cache_invalidate_prefix(_cache_key(project_id, "orders"))

