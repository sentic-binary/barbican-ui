"""Consumer management routes."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, request, url_for

from app import barbican
from app.barbican import BarbicanError
from app.routes.helpers import get_auth, login_required

consumers_bp = Blueprint("consumers", __name__, url_prefix="/consumers")


@consumers_bp.route("/<container_id>/create", methods=["POST"])
@login_required
def create_consumer(container_id: str):
    auth = get_auth()
    name = request.form.get("name", "").strip()
    consumer_url = request.form.get("url", "").strip()

    if not name or not consumer_url:
        flash("Consumer name and URL are required.", "warning")
        return redirect(url_for("containers.get_container", container_id=container_id))

    try:
        barbican.consumer_create(
            auth.barbican_endpoint, auth.token, auth.project_id,
            container_id, name=name, url=consumer_url,
        )
        flash("Consumer registered.", "success")
    except BarbicanError as exc:
        flash(str(exc), "danger")

    return redirect(url_for("containers.get_container", container_id=container_id))


@consumers_bp.route("/<container_id>/delete", methods=["POST"])
@login_required
def delete_consumer(container_id: str):
    auth = get_auth()
    name = request.form.get("name", "").strip()
    consumer_url = request.form.get("url", "").strip()

    try:
        barbican.consumer_delete(
            auth.barbican_endpoint, auth.token, auth.project_id,
            container_id, name=name, url=consumer_url,
        )
        flash("Consumer removed.", "success")
    except BarbicanError as exc:
        flash(str(exc), "danger")

    return redirect(url_for("containers.get_container", container_id=container_id))

