"""Route helpers – session management and login_required decorator."""

from __future__ import annotations

import re
from functools import wraps
from typing import Any

from flask import abort, redirect, request, session, url_for, flash

from app.auth import AuthToken
from app.config import Config

# Valid UUID pattern for resource IDs
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$"
    r"|^[a-zA-Z0-9_-]+$"
)


def get_auth() -> AuthToken | None:
    """Return the current AuthToken from the session, or None."""
    data = session.get("auth")
    if data is None:
        return None
    try:
        # IP binding check — reject session if IP changed
        if Config.SESSION_BIND_IP:
            stored_ip = data.get("client_ip", "")
            current_ip = request.remote_addr or ""
            if stored_ip and current_ip and stored_ip != current_ip:
                session.clear()
                return None

        from datetime import datetime
        token = AuthToken(
            token=data["token"],
            expires_at=datetime.fromisoformat(data["expires_at"]),
            project_id=data["project_id"],
            project_name=data["project_name"],
            user_id=data["user_id"],
            user_name=data["user_name"],
            barbican_endpoint=data["barbican_endpoint"],
            catalog=[],
        )
        if token.is_expired:
            session.clear()
            return None
        return token
    except (KeyError, TypeError, ValueError):
        session.clear()
        return None


def save_auth(token: AuthToken) -> None:
    """Persist an AuthToken into the Flask session."""
    session["auth"] = {
        "token": token.token,
        "expires_at": token.expires_at.isoformat(),
        "project_id": token.project_id,
        "project_name": token.project_name,
        "user_id": token.user_id,
        "user_name": token.user_name,
        "barbican_endpoint": token.barbican_endpoint,
        "client_ip": request.remote_addr or "",
    }
    session.permanent = True


def login_required(f):
    """Decorator that redirects to login if not authenticated."""
    @wraps(f)
    def decorated(*args: Any, **kwargs: Any):
        auth = get_auth()
        if auth is None:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def _extract_id(href: str) -> str:
    """Extract UUID from a Barbican href like https://host/v1/secrets/UUID."""
    return href.rstrip("/").rsplit("/", 1)[-1] if href else ""


def validate_resource_id(resource_id: str) -> str:
    """Validate that a resource ID looks safe (no path traversal)."""
    if not resource_id or not _UUID_RE.match(resource_id):
        abort(400, description="Invalid resource ID")
    if "/" in resource_id or ".." in resource_id:
        abort(400, description="Invalid resource ID")
    return resource_id


def safe_int(value: str, default: int = 1, minimum: int = 1) -> int:
    """Safely parse an integer from a string, returning default on failure."""
    try:
        result = int(value)
        return max(result, minimum)
    except (ValueError, TypeError):
        return default
