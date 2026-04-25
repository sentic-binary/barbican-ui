"""Order management routes."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app import barbican
from app.barbican import BarbicanError
from app.routes.helpers import get_auth, login_required, _extract_id, validate_resource_id, safe_int, safe_error_message

orders_bp = Blueprint("orders", __name__, url_prefix="/orders")


@orders_bp.route("/")
@login_required
def list_orders():
    auth = get_auth()
    page = safe_int(request.args.get("page", "1"))
    limit = 20
    offset = (page - 1) * limit

    try:
        data = barbican.order_list(
            auth.barbican_endpoint, auth.token, auth.project_id,
            limit=limit, offset=offset,
        )
    except BarbicanError as exc:
        flash(safe_error_message(exc), "danger")
        data = {"orders": [], "total": 0}

    orders = data.get("orders", [])
    total = data.get("total", len(orders))
    for o in orders:
        o["id"] = _extract_id(o.get("order_ref", ""))

    return render_template(
        "orders/list.html",
        orders=orders,
        total=total,
        page=page,
        limit=limit,
        auth=auth,
    )


@orders_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_order():
    auth = get_auth()
    if request.method == "GET":
        return render_template("orders/create.html", auth=auth)

    order_type = request.form.get("type", "key")
    name = request.form.get("name", "").strip()
    algorithm = request.form.get("algorithm", "aes").strip()
    bit_length = request.form.get("bit_length", "256").strip()
    mode = request.form.get("mode", "cbc").strip()
    payload_content_type = request.form.get("payload_content_type", "application/octet-stream").strip()
    expiration = request.form.get("expiration", "").strip()

    meta: dict = {
        "name": name,
        "algorithm": algorithm,
        "bit_length": int(bit_length) if bit_length else 256,
        "mode": mode,
        "payload_content_type": payload_content_type,
    }
    if expiration:
        meta["expiration"] = expiration

    try:
        result = barbican.order_create(
            auth.barbican_endpoint, auth.token, auth.project_id,
            order_type=order_type, meta=meta,
        )
        oid = _extract_id(result.get("order_ref", ""))
        flash("Order created.", "success")
        return redirect(url_for("orders.get_order", order_id=oid))
    except BarbicanError as exc:
        flash(safe_error_message(exc), "danger")
        return redirect(url_for("orders.create_order"))


@orders_bp.route("/<order_id>")
@login_required
def get_order(order_id: str):
    validate_resource_id(order_id)
    auth = get_auth()
    try:
        order = barbican.order_get(
            auth.barbican_endpoint, auth.token, auth.project_id, order_id
        )
    except BarbicanError as exc:
        flash(safe_error_message(exc), "danger")
        return redirect(url_for("orders.list_orders"))

    order["id"] = order_id
    if order.get("secret_ref"):
        order["secret_id"] = _extract_id(order["secret_ref"])

    return render_template("orders/detail.html", order=order, auth=auth)


@orders_bp.route("/<order_id>/delete", methods=["POST"])
@login_required
def delete_order(order_id: str):
    validate_resource_id(order_id)
    auth = get_auth()
    try:
        barbican.order_delete(
            auth.barbican_endpoint, auth.token, auth.project_id, order_id
        )
        flash("Order deleted.", "success")
    except BarbicanError as exc:
        flash(safe_error_message(exc), "danger")
    return redirect(url_for("orders.list_orders"))

