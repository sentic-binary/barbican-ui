"""Barbican UI – Keystone v3 authentication helpers.

Only ONE Keystone endpoint is ever called:
    POST /v3/auth/tokens  (password authentication with project scope)

This requires no admin privileges — any valid OpenStack user can obtain a
scoped token for projects they have access to.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from app.config import Config

logger = logging.getLogger(__name__)


@dataclass
class AuthToken:
    """Represents a scoped Keystone token with its metadata."""

    token: str
    expires_at: datetime
    project_id: str
    project_name: str
    user_id: str
    user_name: str
    barbican_endpoint: str  # resolved endpoint for the key-manager service
    catalog: list[dict[str, Any]]

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at


class AuthError(Exception):
    """Raised when Keystone authentication fails."""


def authenticate(
    username: str,
    password: str,
    project_name: str = "",
    project_id: str = "",
    user_domain_name: str = "",
    project_domain_name: str = "",
    region: str = "",
) -> AuthToken:
    """Authenticate against Keystone v3 and return an AuthToken.

    Parameters fall back to Config defaults when not provided.
    """
    auth_url = Config.OS_AUTH_URL.rstrip("/")
    user_domain = user_domain_name or Config.OS_USER_DOMAIN_NAME
    proj_domain = project_domain_name or Config.OS_PROJECT_DOMAIN_NAME

    # Build identity payload
    identity: dict[str, Any] = {
        "methods": ["password"],
        "password": {
            "user": {
                "name": username,
                "password": password,
                "domain": {"name": user_domain},
            }
        },
    }

    # Build scope — prefer project name, fall back to ID
    scope: dict[str, Any] = {}
    p_name = project_name or Config.OS_TENANT_NAME
    p_id = project_id or Config.OS_TENANT_ID
    if p_name:
        scope = {
            "project": {
                "name": p_name,
                "domain": {"name": proj_domain},
            }
        }
    elif p_id:
        scope = {"project": {"id": p_id}}

    body: dict[str, Any] = {"auth": {"identity": identity}}
    if scope:
        body["auth"]["scope"] = scope

    try:
        resp = requests.post(
            f"{auth_url}/auth/tokens",
            json=body,
            headers={"Content-Type": "application/json"},
            timeout=30,
            verify=Config.tls_verify(),
        )
    except requests.RequestException as exc:
        logger.error("Keystone connection error: %s", exc)
        raise AuthError(f"Cannot connect to Keystone at {auth_url}") from exc

    if resp.status_code not in (200, 201):
        detail = ""
        try:
            detail = resp.json().get("error", {}).get("message", resp.text[:200])
        except Exception:
            detail = resp.text[:200]
        logger.warning("Keystone auth failed (%s): %s", resp.status_code, detail)
        raise AuthError(f"Authentication failed: {detail}")

    token_str = resp.headers.get("X-Subject-Token", "")
    data = resp.json().get("token", {})

    expires_str = data.get("expires_at", "")
    try:
        expires_at = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        expires_at = datetime.now(timezone.utc)

    catalog = data.get("catalog", [])
    effective_region = region or Config.OS_REGION_NAME
    barbican_endpoint = _resolve_barbican_endpoint(catalog, effective_region)

    project = data.get("project", {})

    return AuthToken(
        token=token_str,
        expires_at=expires_at,
        project_id=project.get("id", ""),
        project_name=project.get("name", ""),
        user_id=data.get("user", {}).get("id", ""),
        user_name=data.get("user", {}).get("name", ""),
        barbican_endpoint=barbican_endpoint,
        catalog=catalog,
    )


def _resolve_barbican_endpoint(catalog: list[dict[str, Any]], region: str = "") -> str:
    """Determine the Barbican endpoint to use.

    Priority:
    1. OS_BARBICAN_ENDPOINT env var (always wins)
    2. Autodiscovery from the service catalog (if enabled)
    3. Empty string (will fail on first Barbican call)
    """
    # 1. Explicit override
    if Config.OS_BARBICAN_ENDPOINT:
        return Config.OS_BARBICAN_ENDPOINT.rstrip("/")

    # 2. Autodiscovery
    if Config.BARBICAN_ENDPOINT_AUTODISCOVERY:
        for svc in catalog:
            if svc.get("type") == "key-manager":
                # First pass: match by region if specified
                if region:
                    for ep in svc.get("endpoints", []):
                        if ep.get("interface") == "public":
                            if ep.get("region") == region or ep.get("region_id") == region:
                                url = ep.get("url", "").rstrip("/")
                                logger.info("Barbican endpoint discovered (region=%s): %s", region, url)
                                return url
                    logger.warning("No key-manager endpoint in region '%s', falling back to first public endpoint", region)

                # Second pass (or no region): take first public endpoint
                for ep in svc.get("endpoints", []):
                    if ep.get("interface") == "public":
                        url = ep.get("url", "").rstrip("/")
                        ep_region = ep.get("region") or ep.get("region_id") or "unknown"
                        logger.info("Barbican endpoint discovered (region=%s): %s", ep_region, url)
                        return url

        logger.warning("key-manager service not found in catalog")

    return ""

