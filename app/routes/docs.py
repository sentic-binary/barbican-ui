"""In-app documentation route."""

from flask import Blueprint, render_template

from app.routes.helpers import get_auth, login_required

docs_bp = Blueprint("docs", __name__)


@docs_bp.route("/docs")
@login_required
def documentation():
    auth = get_auth()
    return render_template("docs.html", auth=auth)

