"""Secret management routes with virtual folder browsing."""

from __future__ import annotations

import json
from collections import defaultdict

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import barbican
from app.barbican import BarbicanError
from app.routes.helpers import get_auth, login_required, _extract_id, validate_resource_id, safe_error_message

secrets_bp = Blueprint("secrets", __name__, url_prefix="/secrets")

PATH_SEP = "/"


def _build_folder_tree(secrets: list[dict]) -> dict:
    """Build virtual folder paths from secret names using '/' as separator."""
    all_paths: set[str] = set()
    for s in secrets:
        name = s.get("name", "") or ""
        parts = name.split(PATH_SEP)
        if len(parts) > 1:
            for i in range(1, len(parts)):
                all_paths.add(PATH_SEP.join(parts[:i]))
    return {"all_paths": sorted(all_paths)}


def _filter_by_path(secrets: list[dict], path: str) -> tuple[list[dict], list[dict]]:
    """Return (subfolder_info_list, secrets_in_this_folder) for a path prefix."""
    prefix = (path + PATH_SEP) if path else ""
    subfolder_counts: dict[str, int] = defaultdict(int)
    current_secrets: list[dict] = []

    for s in secrets:
        name = s.get("name", "") or ""
        if not prefix:
            if PATH_SEP in name:
                subfolder_counts[name.split(PATH_SEP)[0]] += 1
            else:
                current_secrets.append(s)
        else:
            if name.startswith(prefix):
                remainder = name[len(prefix):]
                if PATH_SEP in remainder:
                    subfolder_counts[remainder.split(PATH_SEP)[0]] += 1
                else:
                    current_secrets.append(s)

    subfolder_info = [
        {"name": sf, "count": cnt}
        for sf, cnt in sorted(subfolder_counts.items())
    ]
    return subfolder_info, current_secrets


@secrets_bp.route("/")
@login_required
def list_secrets():
    auth = get_auth()
    path = request.args.get("path", "").strip().strip(PATH_SEP)
    name_filter = request.args.get("name", "")

    try:
        all_data = barbican.secret_list(
            auth.barbican_endpoint, auth.token, auth.project_id,
            limit=500, offset=0, name=name_filter,
        )
    except BarbicanError as exc:
        flash(safe_error_message(exc), "danger")
        all_data = {"secrets": [], "total": 0}

    all_secrets = all_data.get("secrets", [])
    total = all_data.get("total", len(all_secrets))

    for s in all_secrets:
        s["id"] = _extract_id(s.get("secret_ref", ""))

    tree = _build_folder_tree(all_secrets)

    if name_filter:
        subfolders = []
        current_secrets = all_secrets
    else:
        subfolders, current_secrets = _filter_by_path(all_secrets, path)

    # Breadcrumb
    breadcrumb = []
    if path:
        parts = path.split(PATH_SEP)
        for i, part in enumerate(parts):
            breadcrumb.append({"name": part, "path": PATH_SEP.join(parts[:i + 1])})

    # Short names for display
    for s in current_secrets:
        full_name = s.get("name", "") or ""
        s["short_name"] = full_name.rsplit(PATH_SEP, 1)[-1] if PATH_SEP in full_name else full_name

    return render_template(
        "secrets/list.html",
        secrets=current_secrets, subfolders=subfolders, total=total,
        path=path, breadcrumb=breadcrumb, name_filter=name_filter,
        all_paths=tree["all_paths"], auth=auth,
    )


@secrets_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_secret():
    auth = get_auth()

    if request.method == "GET":
        path_prefix = request.args.get("path", "").strip().strip(PATH_SEP)
        clone_from = request.args.get("clone_from", "").strip()
        replace_for = request.args.get("replace_for", "").strip()
        source_id = clone_from or replace_for
        is_replace = bool(replace_for)

        # Fetch folder tree for autocomplete
        try:
            all_data = barbican.secret_list(
                auth.barbican_endpoint, auth.token, auth.project_id, limit=500
            )
            all_secrets = all_data.get("secrets", [])
        except BarbicanError:
            all_secrets = []
        tree = _build_folder_tree(all_secrets)

        # Clone/Replace: pre-fill from existing secret
        clone_data = {}
        if source_id:
            try:
                validate_resource_id(source_id)
                meta = barbican.secret_get(
                    auth.barbican_endpoint, auth.token, auth.project_id, source_id
                )
                original_name = meta.get("name", "") or ""
                # Split into path + short name
                if PATH_SEP in original_name:
                    clone_path, clone_short = original_name.rsplit(PATH_SEP, 1)
                    path_prefix = clone_path
                else:
                    clone_short = original_name

                if is_replace:
                    clone_data["name"] = clone_short
                    clone_data["replace_id"] = source_id
                else:
                    clone_data["name"] = clone_short + "-copy" if clone_short else ""

                clone_data["secret_type"] = meta.get("secret_type", "opaque")
                clone_data["algorithm"] = meta.get("algorithm", "") or ""
                clone_data["bit_length"] = meta.get("bit_length", "") or ""
                clone_data["mode"] = meta.get("mode", "") or ""
                clone_data["expiration"] = meta.get("expiration", "") or ""

                # Try to fetch payload
                if meta.get("status") == "ACTIVE":
                    try:
                        ct = meta.get("content_types", {})
                        accept = ct.get("default", "text/plain") if ct else "text/plain"
                        clone_data["payload"] = barbican.secret_get_payload(
                            auth.barbican_endpoint, auth.token, auth.project_id,
                            source_id, accept=accept,
                        )
                        clone_data["payload_content_type"] = accept
                    except BarbicanError:
                        clone_data["payload"] = ""
                        clone_data["payload_content_type"] = "text/plain"

                # Try to fetch user metadata
                try:
                    user_meta = barbican.secret_metadata_get(
                        auth.barbican_endpoint, auth.token, auth.project_id, source_id
                    )
                    clone_data["user_metadata"] = user_meta
                except BarbicanError:
                    clone_data["user_metadata"] = {}
            except (BarbicanError, ValueError, Exception):
                pass

        return render_template(
            "secrets/create.html", auth=auth,
            path_prefix=path_prefix, all_paths=tree["all_paths"],
            clone=clone_data,
        )

    # POST — build full name from path + name
    path_prefix = request.form.get("path_prefix", "").strip().strip(PATH_SEP)
    short_name = request.form.get("name", "").strip()
    if path_prefix and short_name:
        name = path_prefix + PATH_SEP + short_name
    else:
        name = short_name or path_prefix

    secret_type = request.form.get("secret_type", "opaque")
    payload_mode = request.form.get("payload_mode", "simple")
    algorithm = request.form.get("algorithm", "").strip()
    bit_length = request.form.get("bit_length", "")
    mode = request.form.get("mode", "").strip()
    expiration = request.form.get("expiration", "").strip()
    replace_id = request.form.get("replace_id", "").strip()

    if payload_mode == "kv":
        keys = request.form.getlist("kv_key")
        values = request.form.getlist("kv_value")
        payload_dict = {k.strip(): v for k, v in zip(keys, values) if k.strip()}
        payload = json.dumps(payload_dict, indent=2)
        content_type = "text/plain"
    elif payload_mode == "json":
        payload = request.form.get("json_payload", "").strip()
        content_type = "text/plain"
    else:
        payload = request.form.get("payload", "")
        content_type = request.form.get("payload_content_type", "text/plain")

    # Replace mode: delete the old secret first
    if replace_id:
        try:
            validate_resource_id(replace_id)
            barbican.secret_delete(
                auth.barbican_endpoint, auth.token, auth.project_id, replace_id
            )
        except BarbicanError as exc:
            flash(f"Failed to delete original secret: {safe_error_message(exc)}", "danger")
            return redirect(url_for("secrets.get_secret", secret_id=replace_id))

    try:
        result = barbican.secret_store(
            auth.barbican_endpoint, auth.token, auth.project_id,
            name=name, payload=payload, payload_content_type=content_type,
            secret_type=secret_type, algorithm=algorithm,
            bit_length=int(bit_length) if bit_length else 0,
            mode=mode, expiration=expiration,
        )
        secret_id = _extract_id(result.get("secret_ref", ""))
        if replace_id:
            flash("Secret replaced successfully.", "success")
        else:
            flash("Secret created successfully.", "success")
        return redirect(url_for("secrets.get_secret", secret_id=secret_id))
    except BarbicanError as exc:
        flash(safe_error_message(exc), "danger")
        return redirect(url_for("secrets.create_secret"))


@secrets_bp.route("/<secret_id>")
@login_required
def get_secret(secret_id: str):
    validate_resource_id(secret_id)
    auth = get_auth()
    try:
        meta = barbican.secret_get(
            auth.barbican_endpoint, auth.token, auth.project_id, secret_id
        )
    except BarbicanError as exc:
        flash(safe_error_message(exc), "danger")
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

    payload_json = None
    if payload:
        try:
            payload_json = json.loads(payload)
            if not isinstance(payload_json, dict):
                payload_json = None
        except (json.JSONDecodeError, TypeError):
            pass

    meta["id"] = secret_id

    # Fetch user metadata
    user_metadata = {}
    try:
        user_metadata = barbican.secret_metadata_get(
            auth.barbican_endpoint, auth.token, auth.project_id, secret_id
        )
    except BarbicanError:
        pass

    # Derive parent path for back navigation
    secret_name = meta.get("name", "") or ""
    parent_path = ""
    if PATH_SEP in secret_name:
        parent_path = secret_name.rsplit(PATH_SEP, 1)[0]

    return render_template(
        "secrets/detail.html",
        secret=meta, payload=payload, payload_json=payload_json,
        payload_error=payload_error, parent_path=parent_path, auth=auth,
        user_metadata=user_metadata,
    )


@secrets_bp.route("/<secret_id>/update", methods=["POST"])
@login_required
def update_secret(secret_id: str):
    validate_resource_id(secret_id)
    auth = get_auth()
    payload_mode = request.form.get("payload_mode", "simple")

    if payload_mode == "kv":
        keys = request.form.getlist("kv_key")
        values = request.form.getlist("kv_value")
        payload_dict = {k.strip(): v for k, v in zip(keys, values) if k.strip()}
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
            auth.barbican_endpoint, auth.token, auth.project_id,
            secret_id, payload=payload, payload_content_type=content_type,
        )
        flash("Secret payload updated.", "success")
    except BarbicanError as exc:
        flash(safe_error_message(exc), "danger")

    return redirect(url_for("secrets.get_secret", secret_id=secret_id))


@secrets_bp.route("/<secret_id>/delete", methods=["POST"])
@login_required
def delete_secret(secret_id: str):
    validate_resource_id(secret_id)
    auth = get_auth()
    try:
        barbican.secret_delete(
            auth.barbican_endpoint, auth.token, auth.project_id, secret_id
        )
        flash("Secret deleted.", "success")
    except BarbicanError as exc:
        flash(safe_error_message(exc), "danger")

    return redirect(url_for("secrets.list_secrets"))


@secrets_bp.route("/<secret_id>/metadata/add", methods=["POST"])
@login_required
def add_metadata(secret_id: str):
    validate_resource_id(secret_id)
    auth = get_auth()
    key = request.form.get("meta_key", "").strip()
    value = request.form.get("meta_value", "").strip()
    if not key:
        flash("Metadata key cannot be empty.", "warning")
        return redirect(url_for("secrets.get_secret", secret_id=secret_id))
    try:
        barbican.secret_metadata_update(
            auth.barbican_endpoint, auth.token, auth.project_id,
            secret_id, key=key, value=value,
        )
        flash(f"Metadata '{key}' added.", "success")
    except BarbicanError as exc:
        flash(safe_error_message(exc), "danger")
    return redirect(url_for("secrets.get_secret", secret_id=secret_id))


@secrets_bp.route("/<secret_id>/metadata/delete", methods=["POST"])
@login_required
def delete_metadata(secret_id: str):
    validate_resource_id(secret_id)
    auth = get_auth()
    key = request.form.get("meta_key", "").strip()
    if not key:
        flash("Metadata key cannot be empty.", "warning")
        return redirect(url_for("secrets.get_secret", secret_id=secret_id))
    try:
        barbican.secret_metadata_delete(
            auth.barbican_endpoint, auth.token, auth.project_id,
            secret_id, key=key,
        )
        flash(f"Metadata '{key}' removed.", "success")
    except BarbicanError as exc:
        flash(safe_error_message(exc), "danger")
    return redirect(url_for("secrets.get_secret", secret_id=secret_id))
