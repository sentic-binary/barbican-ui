"""Authentication routes – login / logout."""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.auth import AuthError, authenticate
from app.config import Config
from app.routes.helpers import get_auth, save_auth

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)

# Regex to detect OpenStack-style UUIDs (32 hex chars, with or without dashes)
_HEX_ID_RE = re.compile(r"^[0-9a-fA-F]{32}$|^[0-9a-fA-F-]{36}$")

# Simple in-memory rate limiter for login attempts
_login_attempts: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 10  # max attempts per window


def _is_rate_limited(ip: str) -> bool:
    """Check if an IP has exceeded the login rate limit."""
    now = time.monotonic()
    attempts = _login_attempts[ip]
    # Prune old entries
    _login_attempts[ip] = [t for t in attempts if now - t < _RATE_LIMIT_WINDOW]
    if not _login_attempts[ip]:
        del _login_attempts[ip]
        return False
    # Prevent unbounded growth: evict stale IPs periodically
    if len(_login_attempts) > 10000:
        stale = [k for k, v in _login_attempts.items() if not v or now - v[-1] > _RATE_LIMIT_WINDOW]
        for k in stale:
            del _login_attempts[k]
    return len(_login_attempts.get(ip, [])) >= _RATE_LIMIT_MAX


def _record_attempt(ip: str) -> None:
    _login_attempts[ip].append(time.monotonic())


@auth_bp.route("/")
def index():
    if get_auth():
        return redirect(url_for("secrets.list_secrets"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # Pre-fill default: prefer tenant name, fall back to ID
    default_tenant = Config.OS_TENANT_NAME or Config.OS_TENANT_ID

    if request.method == "GET":
        return render_template(
            "login.html",
            os_auth_url=Config.OS_AUTH_URL,
            default_user_domain=Config.OS_USER_DOMAIN_NAME,
            default_project_domain=Config.OS_PROJECT_DOMAIN_NAME,
            default_tenant_value=default_tenant,
            default_region=Config.OS_REGION_NAME,
        )

    # Rate limiting
    client_ip = request.remote_addr or "unknown"
    if _is_rate_limited(client_ip):
        logger.warning("Rate limit exceeded for IP %s", client_ip)
        flash("Too many login attempts. Please wait a minute.", "danger")
        return redirect(url_for("auth.login"))
    _record_attempt(client_ip)

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    tenant_value = request.form.get("tenant_value", "").strip()
    tenant_type = request.form.get("tenant_type", "auto")
    region = request.form.get("region", "").strip()
    user_domain = request.form.get("user_domain_name", "").strip()
    project_domain = request.form.get("project_domain_name", "").strip()

    if not username or not password:
        flash("Username and password are required.", "danger")
        return redirect(url_for("auth.login"))

    # Resolve tenant_value into project_name or project_id
    project_name = ""
    project_id = ""
    if tenant_type == "name":
        project_name = tenant_value
    elif tenant_type == "id":
        project_id = tenant_value
    else:  # auto
        if _HEX_ID_RE.match(tenant_value.replace("-", "")):
            project_id = tenant_value
        else:
            project_name = tenant_value

    # Override region for this session if provided
    effective_region = region or Config.OS_REGION_NAME

    try:
        token = authenticate(
            username=username,
            password=password,
            project_name=project_name,
            project_id=project_id,
            user_domain_name=user_domain,
            project_domain_name=project_domain,
            region=effective_region,
        )
    except AuthError as exc:
        logger.warning("Login failed for user '%s': %s", username, exc)
        flash("Authentication failed. Please check your credentials.", "danger")
        return redirect(url_for("auth.login"))

    if not token.barbican_endpoint:
        flash(
            "Could not determine Barbican endpoint. "
            "Set OS_BARBICAN_ENDPOINT or ensure key-manager is in the service catalog.",
            "danger",
        )
        return redirect(url_for("auth.login"))

    # Session fixation protection: clear old session before saving new auth
    session.clear()
    save_auth(token)
    flash(f"Logged in as {token.user_name} ({token.project_name})", "success")
    return redirect(url_for("secrets.list_secrets"))


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("auth.login"))
