"""Authentication routes – login / logout."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.auth import AuthError, authenticate
from app.config import Config
from app.routes.helpers import get_auth, save_auth

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/")
def index():
    if get_auth():
        return redirect(url_for("secrets.list_secrets"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template(
            "login.html",
            os_auth_url=Config.OS_AUTH_URL,
            default_user_domain=Config.OS_USER_DOMAIN_NAME,
            default_project_domain=Config.OS_PROJECT_DOMAIN_NAME,
            default_project_name=Config.OS_TENANT_NAME,
            default_project_id=Config.OS_TENANT_ID,
        )

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    project_name = request.form.get("project_name", "").strip()
    project_id = request.form.get("project_id", "").strip()
    user_domain = request.form.get("user_domain_name", "").strip()
    project_domain = request.form.get("project_domain_name", "").strip()

    if not username or not password:
        flash("Username and password are required.", "danger")
        return redirect(url_for("auth.login"))

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

