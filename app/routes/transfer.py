"""Export / Import routes for migrating secrets between Barbican instances."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from flask import Blueprint, flash, redirect, render_template, request, url_for, Response

from app import barbican
from app.barbican import BarbicanError
from app.routes.helpers import get_auth, login_required, _extract_id, safe_error_message

transfer_bp = Blueprint("transfer", __name__, url_prefix="/transfer")
logger = logging.getLogger(__name__)


@transfer_bp.route("/")
@login_required
def index():
    auth = get_auth()
    return render_template("transfer/index.html", auth=auth)


@transfer_bp.route("/export", methods=["POST"])
@login_required
def export_data():
    """Export secrets and containers as a downloadable JSON file."""
    auth = get_auth()
    include_secrets = "secrets" in request.form.getlist("include")
    include_containers = "containers" in request.form.getlist("include")
    include_payloads = "payloads" in request.form.getlist("include")

    export = {
        "version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source_endpoint": auth.barbican_endpoint,
        "project_id": auth.project_id,
        "project_name": auth.project_name,
        "secrets": [],
        "containers": [],
    }

    secret_id_to_name: dict[str, str] = {}

    # ── Export secrets ──────────────────────────────────────────
    if include_secrets or include_containers:
        try:
            data = barbican.secret_list(
                auth.barbican_endpoint, auth.token, auth.project_id,
                limit=500, offset=0,
            )
            all_secrets = data.get("secrets", [])
        except BarbicanError as exc:
            flash(f"Failed to list secrets: {safe_error_message(exc)}", "danger")
            return redirect(url_for("transfer.index"))

        for s in all_secrets:
            secret_id = _extract_id(s.get("secret_ref", ""))
            secret_name = s.get("name", "") or secret_id
            secret_id_to_name[secret_id] = secret_name

            if not include_secrets:
                continue

            entry = {
                "name": s.get("name", ""),
                "secret_type": s.get("secret_type", "opaque"),
                "algorithm": s.get("algorithm"),
                "bit_length": s.get("bit_length"),
                "mode": s.get("mode"),
                "expiration": s.get("expiration"),
                "payload": None,
                "payload_content_type": None,
            }

            # Optionally fetch payload
            if include_payloads and s.get("status") == "ACTIVE":
                try:
                    ct = s.get("content_types", {})
                    accept = ct.get("default", "text/plain") if ct else "text/plain"
                    payload = barbican.secret_get_payload(
                        auth.barbican_endpoint, auth.token, auth.project_id,
                        secret_id, accept=accept,
                    )
                    entry["payload"] = payload
                    entry["payload_content_type"] = accept
                except BarbicanError as exc:
                    logger.warning("Could not fetch payload for %s: %s", secret_id, exc)
                    entry["payload_error"] = str(exc)

            export["secrets"].append(entry)

    # ── Export containers ───────────────────────────────────────
    if include_containers:
        try:
            data = barbican.container_list(
                auth.barbican_endpoint, auth.token, auth.project_id,
                limit=500, offset=0,
            )
            all_containers = data.get("containers", [])
        except BarbicanError as exc:
            flash(f"Failed to list containers: {safe_error_message(exc)}", "danger")
            return redirect(url_for("transfer.index"))

        for c in all_containers:
            container_id = _extract_id(c.get("container_ref", ""))
            secret_refs = []
            for sr in c.get("secret_refs", []):
                sid = _extract_id(sr.get("secret_ref", ""))
                secret_refs.append({
                    "name": sr.get("name", ""),
                    "secret_name": secret_id_to_name.get(sid, sid),
                })

            # Fetch consumers
            consumers = []
            try:
                cons_data = barbican.consumer_list(
                    auth.barbican_endpoint, auth.token, auth.project_id,
                    container_id,
                )
                consumers = [
                    {"name": co.get("name", ""), "url": co.get("URL", "")}
                    for co in cons_data.get("consumers", [])
                ]
            except BarbicanError:
                pass

            export["containers"].append({
                "name": c.get("name", ""),
                "type": c.get("type", "generic"),
                "secret_refs": secret_refs,
                "consumers": consumers,
            })

    # Build filename (sanitize project name for safe filenames)
    safe_project = "".join(c for c in auth.project_name if c.isalnum() or c in "-_.")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"barbican_export_{safe_project}_{timestamp}.json"

    return Response(
        json.dumps(export, indent=2, ensure_ascii=False),
        mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@transfer_bp.route("/import", methods=["POST"])
@login_required
def import_data():
    """Import secrets and containers from a previously exported JSON file."""
    auth = get_auth()

    file = request.files.get("file")
    if not file or not file.filename:
        flash("Please select a JSON file to import.", "warning")
        return redirect(url_for("transfer.index"))

    dry_run = "dry_run" in request.form
    skip_existing = "skip_existing" in request.form

    try:
        content = file.read().decode("utf-8")
        data = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        flash(f"Invalid JSON file: {safe_error_message(exc)}", "danger")
        return redirect(url_for("transfer.index"))

    if data.get("version") != "1.0":
        flash(f"Unsupported export version: {data.get('version')}", "danger")
        return redirect(url_for("transfer.index"))

    results = {
        "secrets_created": 0,
        "secrets_skipped": 0,
        "secrets_failed": 0,
        "containers_created": 0,
        "containers_skipped": 0,
        "containers_failed": 0,
        "consumers_created": 0,
        "errors": [],
    }

    # Map: secret name → new secret ID (for container references)
    name_to_new_id: dict[str, str] = {}

    # Get existing secrets to check for duplicates
    existing_names: set[str] = set()
    if skip_existing:
        try:
            existing = barbican.secret_list(
                auth.barbican_endpoint, auth.token, auth.project_id,
                limit=500, offset=0,
            )
            for s in existing.get("secrets", []):
                if s.get("name"):
                    existing_names.add(s["name"])
        except BarbicanError:
            pass

    # ── Import secrets ──────────────────────────────────────────
    for secret in data.get("secrets", []):
        name = secret.get("name", "")

        if skip_existing and name in existing_names:
            results["secrets_skipped"] += 1
            logger.info("Skipping existing secret: %s", name)
            continue

        if dry_run:
            results["secrets_created"] += 1
            continue

        payload = secret.get("payload")
        content_type = secret.get("payload_content_type", "text/plain")

        try:
            result = barbican.secret_store(
                auth.barbican_endpoint, auth.token, auth.project_id,
                name=name,
                payload=payload or "",
                payload_content_type=content_type or "text/plain",
                secret_type=secret.get("secret_type", "opaque"),
                algorithm=secret.get("algorithm", ""),
                bit_length=secret.get("bit_length") or 0,
                mode=secret.get("mode", ""),
                expiration=secret.get("expiration", ""),
            )
            new_id = _extract_id(result.get("secret_ref", ""))
            name_to_new_id[name] = new_id
            results["secrets_created"] += 1
        except BarbicanError as exc:
            results["secrets_failed"] += 1
            results["errors"].append(f"Secret '{name}': {exc}")
            logger.error("Failed to import secret '%s': %s", name, exc)

    # If not dry run, also map existing secrets by name for container refs
    if not dry_run and skip_existing:
        try:
            all_secrets = barbican.secret_list(
                auth.barbican_endpoint, auth.token, auth.project_id,
                limit=500, offset=0,
            )
            for s in all_secrets.get("secrets", []):
                sname = s.get("name", "")
                if sname and sname not in name_to_new_id:
                    name_to_new_id[sname] = _extract_id(s.get("secret_ref", ""))
        except BarbicanError:
            pass

    # ── Import containers ───────────────────────────────────────
    for container in data.get("containers", []):
        cname = container.get("name", "")

        if dry_run:
            results["containers_created"] += 1
            continue

        # Resolve secret references by name
        secret_refs = []
        for sr in container.get("secret_refs", []):
            secret_name = sr.get("secret_name", "")
            new_id = name_to_new_id.get(secret_name)
            if not new_id:
                results["errors"].append(
                    f"Container '{cname}': secret '{secret_name}' not found, skipping reference"
                )
                continue
            secret_refs.append({
                "name": sr.get("name", ""),
                "secret_ref": f"{auth.barbican_endpoint}/v1/secrets/{new_id}",
            })

        try:
            result = barbican.container_create(
                auth.barbican_endpoint, auth.token, auth.project_id,
                name=cname,
                container_type=container.get("type", "generic"),
                secret_refs=secret_refs,
            )
            new_container_id = _extract_id(result.get("container_ref", ""))
            results["containers_created"] += 1

            # Re-register consumers
            for cons in container.get("consumers", []):
                try:
                    barbican.consumer_create(
                        auth.barbican_endpoint, auth.token, auth.project_id,
                        new_container_id,
                        name=cons.get("name", ""),
                        url=cons.get("url", ""),
                    )
                    results["consumers_created"] += 1
                except BarbicanError as exc:
                    results["errors"].append(f"Consumer '{cons.get('name')}': {exc}")

        except BarbicanError as exc:
            results["containers_failed"] += 1
            results["errors"].append(f"Container '{cname}': {exc}")
            logger.error("Failed to import container '%s': %s", cname, exc)

    # Flash summary
    prefix = "[DRY RUN] " if dry_run else ""
    flash(
        f"{prefix}Import complete: "
        f"{results['secrets_created']} secrets created, "
        f"{results['secrets_skipped']} skipped, "
        f"{results['secrets_failed']} failed · "
        f"{results['containers_created']} containers created, "
        f"{results['consumers_created']} consumers registered",
        "success" if not results["errors"] else "warning",
    )
    for err in results["errors"][:10]:
        flash(err, "danger")
    if len(results["errors"]) > 10:
        flash(f"... and {len(results['errors']) - 10} more errors", "danger")

    return redirect(url_for("transfer.index"))

