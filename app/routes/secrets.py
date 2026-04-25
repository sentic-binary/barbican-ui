"""Secret management routes."""

from __future__ import annotations

import json

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import barbican
from app.barbican import BarbicanError
from app.routes.helpers import get_auth, login_required, _extract_id

secrets_bp = Blueprint("secrets", __name__, url_prefix="/secrets")


@secrets_bp.route("/")
@login_required
def list_secrets():
    auth = get_auth()
    page = int(request.args.get("page", 1))
    limit = 20
    offset = (page - 1) * limit
    name_filter = request.args.get("name", "")

    try:
        data = barbican.secret_list(
            auth.barbican_endpoint,
            auth.token,
            auth.project_id,
            limit=limit,
            offset=offset,
            name=name_filter,
        )
    except BarbicanError as exc:
        flash(str(exc), "danger")
        data = {"secrets": [], "total": 0}

    secrets = data.get("secrets", [])
    total = data.get("total", len(secrets))

    # Extract IDs from hrefs
    for s in secrets:
        s["id"] = _extract_id(s.get("secret_ref", ""))

    return render_template(
        "secrets/list.html",
        secrets=secrets,
        total=total,
        page=page,
        limit=limit,
        name_filter=name_filter,
        auth=auth,
    )


@secrets_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_secret():
    auth = get_auth()
    if request.method == "GET":
        return render_template("secrets/create.html", auth=auth)

    name = request.form.get("name", "").strip()
    secret_type = request.form.get("secret_type", "opaque")
    payload_mode = request.form.get("payload_mode", "simple")
    algorithm = request.form.get("algorithm", "").strip()
    bit_length = request.form.get("bit_length", "")
    mode = request.form.get("mode", "").strip()
    expiration = request.form.get("expiration", "").strip()

    # Build payload based on mode
    if payload_mode == "kv":
        keys = request.form.getlist("kv_key")
        values = request.form.getlist("kv_value")
        payload_dict = {}
        for k, v in zip(keys, values):
            k = k.strip()
            if k:
                payload_dict[k] = v
        payload = json.dumps(payload_dict, indent=2)
        content_type = "text/plain"
    elif payload_mode == "json":
        payload = request.form.get("json_payload", "").strip()
        content_type = "text/plain"
    else:
        payload = request.form.get("payload", "")
        content_type = request.form.get("payload_content_type", "text/plain")

    try:
        result = barbican.secret_store(
            auth.barbican_endpoint,
            auth.token,
            auth.project_id,
            name=name,
            payload=payload,
            payload_content_type=content_type,
            secret_type=secret_type,
            algorithm=algorithm,
            bit_length=int(bit_length) if bit_length else 0,
            mode=mode,
            expiration=expiration,
        )
        secret_id = _extract_id(result.get("secret_ref", ""))
        flash("Secret created successfully.", "success")
        return redirect(url_for("secrets.get_secret", secret_id=secret_id))
    except BarbicanError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("secrets.create_secret"))


@secrets_bp.route("/<secret_id>")
@login_required
def get_secret(secret_id: str):
    auth = get_auth()
    try:
        meta = barbican.secret_get(
            auth.barbican_endpoint, auth.token, auth.project_id, secret_id
        )
    except BarbicanError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("secrets.list_secrets"))

    payload = None
    payload_error = None
    if meta.get("status") == "ACTIVE":
        try:
            ct = meta.get("content_types", {})
            accept = ct.get("default", "text/plain") if ct else "text/plain"
            payload = barbican.secret_get_payload(
                auth.barbican_endpoint, auth.token, auth.project_id, secret_id,
                accept=accept,
            )
        except BarbicanError as exc:
            payload_error = str(exc)

    # Try to parse payload as JSON for key-value display
    payload_json = None
    if payload:
        try:
            payload_json = json.loads(payload)
            if not isinstance(payload_json, dict):
                payload_json = None
        except (json.JSONDecodeError, TypeError):
            pass

    meta["id"] = secret_id
    return render_template(
        "secrets/detail.html",
        secret=meta,
        payload=payload,
        payload_json=payload_json,
        payload_error=payload_error,
        auth=auth,
    )


@secrets_bp.route("/<secret_id>/update", methods=["POST"])
@login_required
def update_secret(secret_id: str):
    auth = get_auth()
    payload_mode = request.form.get("payload_mode", "simple")

    if payload_mode == "kv":
        keys = request.form.getlist("kv_key")
        values = request.form.getlist("kv_value")
        payload_dict = {}
        for k, v in zip(keys, values):
            k = k.strip()
            if k:
                payload_dict[k] = v
        payload = json.dumps(payload_dict, indent=2)
        content_type = "text/plain"
    elif payload_mode == "json":
        payload = request.form.get("json_payload", "").strip()
        content_type = "text/plain"
    else:
        payload = request.form.get("payload", "")
        content_type = request.form.get("payload_content_type", "text/plain")

    try:
        barbican.secret_update(
            auth.barbican_endpoint,
            auth.token,
            auth.project_id,
            secret_id,
            payload=payload,
            payload_content_type=content_type,
        )
        flash("Secret payload updated.", "success")
    except BarbicanError as exc:
        flash(str(exc), "danger")

    return redirect(url_for("secrets.get_secret", secret_id=secret_id))


@secrets_bp.route("/<secret_id>/delete", methods=["POST"])
@login_required
def delete_secret(secret_id: str):
    auth = get_auth()
    try:
        barbican.secret_delete(
            auth.barbican_endpoint, auth.token, auth.project_id, secret_id
        )
        flash("Secret deleted.", "success")
    except BarbicanError as exc:
        flash(str(exc), "danger")

    return redirect(url_for("secrets.list_secrets"))

