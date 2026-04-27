"""Container management routes."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import barbican
from app.barbican import BarbicanError
from app.routes.helpers import get_auth, login_required, _extract_id, validate_resource_id, safe_int, safe_error_message

containers_bp = Blueprint("containers", __name__, url_prefix="/containers")


@containers_bp.route("/")
@login_required
def list_containers():
    auth = get_auth()
    page = safe_int(request.args.get("page", "1"))
    limit = 20
    offset = (page - 1) * limit

    try:
        data = barbican.container_list(
            auth.barbican_endpoint, auth.token, auth.project_id,
            limit=limit, offset=offset,
        )
    except BarbicanError as exc:
        flash(safe_error_message(exc), "danger")
        data = {"containers": [], "total": 0}

    containers = data.get("containers", [])
    total = data.get("total", len(containers))
    for c in containers:
        c["id"] = _extract_id(c.get("container_ref", ""))

    return render_template(
        "containers/list.html",
        containers=containers,
        total=total,
        page=page,
        limit=limit,
        auth=auth,
    )


@containers_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_container():
    auth = get_auth()

    if request.method == "GET":
        # Fetch secrets for selection
        try:
            sec_data = barbican.secret_list(
                auth.barbican_endpoint, auth.token, auth.project_id, limit=200
            )
            secrets = sec_data.get("secrets", [])
            for s in secrets:
                s["id"] = _extract_id(s.get("secret_ref", ""))
        except BarbicanError:
            secrets = []

        # Clone/Replace: pre-fill from existing container
        clone_data = {}
        clone_from = request.args.get("clone_from", "").strip()
        replace_for = request.args.get("replace_for", "").strip()
        source_id = clone_from or replace_for
        is_replace = bool(replace_for)
        if source_id:
            try:
                validate_resource_id(source_id)
            except Exception:
                flash("Invalid source container ID.", "danger")
                return redirect(url_for("containers.list_containers"))
            try:
                ctr = barbican.container_get(
                    auth.barbican_endpoint, auth.token, auth.project_id, source_id
                )
                original_name = ctr.get("name", "") or ""
                if is_replace:
                    clone_data["name"] = original_name
                    clone_data["replace_id"] = source_id
                else:
                    clone_data["name"] = original_name + "-copy"
                clone_data["type"] = ctr.get("type", "generic")
                clone_refs = []
                for sr in ctr.get("secret_refs", []):
                    clone_refs.append({
                        "name": sr.get("name", ""),
                        "secret_id": _extract_id(sr.get("secret_ref", "")),
                    })
                clone_data["secret_refs"] = clone_refs
            except BarbicanError as exc:
                flash(f"Cannot load source container: {safe_error_message(exc)}", "danger")
                return redirect(url_for("containers.list_containers"))

        return render_template("containers/create.html", auth=auth, secrets=secrets, clone=clone_data)

    name = request.form.get("name", "").strip()
    container_type = request.form.get("type", "generic")
    ref_names = request.form.getlist("ref_name")
    ref_ids = request.form.getlist("ref_id")
    replace_id = request.form.get("replace_id", "").strip()

    secret_refs = []
    for rn, ri in zip(ref_names, ref_ids):
        rn = rn.strip()
        ri = ri.strip()
        if ri:
            secret_refs.append({
                "name": rn if rn else "secret",
                "secret_ref": f"{auth.barbican_endpoint}/v1/secrets/{ri}",
            })

    # Replace mode: save consumers, delete the old container, then re-register them
    old_consumers = []
    if replace_id:
        try:
            validate_resource_id(replace_id)
            # Fetch consumers before deleting
            try:
                c_data = barbican.consumer_list(
                    auth.barbican_endpoint, auth.token, auth.project_id, replace_id
                )
                old_consumers = c_data.get("consumers", [])
            except BarbicanError:
                pass
            # Remove consumers so Barbican allows deletion
            for consumer in old_consumers:
                try:
                    barbican.consumer_delete(
                        auth.barbican_endpoint, auth.token, auth.project_id, replace_id,
                        name=consumer.get("name", ""), url=consumer.get("URL", ""),
                    )
                except BarbicanError:
                    pass
            barbican.container_delete(
                auth.barbican_endpoint, auth.token, auth.project_id, replace_id
            )
        except BarbicanError as exc:
            flash(f"Failed to delete original container: {safe_error_message(exc)}", "danger")
            return redirect(url_for("containers.get_container", container_id=replace_id))

    try:
        result = barbican.container_create(
            auth.barbican_endpoint, auth.token, auth.project_id,
            name=name, container_type=container_type, secret_refs=secret_refs,
        )
        cid = _extract_id(result.get("container_ref", ""))
        # Re-register consumers on the new container
        for consumer in old_consumers:
            try:
                barbican.consumer_create(
                    auth.barbican_endpoint, auth.token, auth.project_id, cid,
                    name=consumer.get("name", ""), url=consumer.get("URL", ""),
                )
            except BarbicanError:
                pass
        if replace_id:
            flash("Container replaced.", "success")
        else:
            flash("Container created.", "success")
        return redirect(url_for("containers.get_container", container_id=cid))
    except BarbicanError as exc:
        flash(safe_error_message(exc), "danger")
        return redirect(url_for("containers.create_container"))


@containers_bp.route("/<container_id>")
@login_required
def get_container(container_id: str):
    validate_resource_id(container_id)
    auth = get_auth()
    try:
        container = barbican.container_get(
            auth.barbican_endpoint, auth.token, auth.project_id, container_id
        )
    except BarbicanError as exc:
        flash(safe_error_message(exc), "danger")
        return redirect(url_for("containers.list_containers"))

    container["id"] = container_id
    for sr in container.get("secret_refs", []):
        sr["secret_id"] = _extract_id(sr.get("secret_ref", ""))

    # Fetch consumers
    consumers = []
    try:
        c_data = barbican.consumer_list(
            auth.barbican_endpoint, auth.token, auth.project_id, container_id
        )
        consumers = c_data.get("consumers", [])
    except BarbicanError:
        pass

    return render_template(
        "containers/detail.html",
        container=container,
        consumers=consumers,
        auth=auth,
    )


@containers_bp.route("/<container_id>/delete", methods=["POST"])
@login_required
def delete_container(container_id: str):
    validate_resource_id(container_id)
    auth = get_auth()
    try:
        barbican.container_delete(
            auth.barbican_endpoint, auth.token, auth.project_id, container_id
        )
        flash("Container deleted.", "success")
    except BarbicanError as exc:
        flash(safe_error_message(exc), "danger")
    return redirect(url_for("containers.list_containers"))

