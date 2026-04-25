"""Route helpers – session management and login_required decorator."""

from __future__ import annotations

from functools import wraps
from typing import Any

from flask import redirect, session, url_for, flash

from app.auth import AuthToken


def get_auth() -> AuthToken | None:
    """Return the current AuthToken from the session, or None."""
    data = session.get("auth")
    if data is None:
        return None
    try:
        from datetime import datetime
        token = AuthToken(
            token=data["token"],
            expires_at=datetime.fromisoformat(data["expires_at"]),
            project_id=data["project_id"],
            project_name=data["project_name"],
            user_id=data["user_id"],
            user_name=data["user_name"],
            barbican_endpoint=data["barbican_endpoint"],
            catalog=data.get("catalog", []),
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
        "catalog": token.catalog,
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

