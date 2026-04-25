"""Authentication routes – login / logout."""

from __future__ import annotations

import re

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.auth import AuthError, authenticate
from app.config import Config
from app.routes.helpers import get_auth, save_auth

auth_bp = Blueprint("auth", __name__)

# Regex to detect OpenStack-style UUIDs (32 hex chars, with or without dashes)
_HEX_ID_RE = re.compile(r"^[0-9a-fA-F]{32}$|^[0-9a-fA-F-]{36}$")


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
    if region:
        Config.OS_REGION_NAME = region

    try:
        token = authenticate(
            username=username,
            password=password,
            project_name=project_name,
            project_id=project_id,
            user_domain_name=user_domain,
            project_domain_name=project_domain,
        )
    except AuthError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("auth.login"))

    if not token.barbican_endpoint:
        flash(
            "Could not determine Barbican endpoint. "
            "Set OS_BARBICAN_ENDPOINT or ensure key-manager is in the service catalog.",
            "danger",
        )
        return redirect(url_for("auth.login"))

    save_auth(token)
    flash(f"Logged in as {token.user_name} ({token.project_name})", "success")
    return redirect(url_for("secrets.list_secrets"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("auth.login"))
