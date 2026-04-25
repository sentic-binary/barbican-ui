"""Barbican UI – Flask application factory."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from flask import Flask

from app.config import Config


def create_app(testing: bool = False) -> Flask:
    """Create and configure the Flask application."""
    load_dotenv()
    Config.validate()

    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
    )

    app.config["SECRET_KEY"] = Config.SECRET_KEY
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = Config.SESSION_LIFETIME_SECONDS
    app.config["WTF_CSRF_ENABLED"] = not testing

    # Logging
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Register blueprints
    from app.routes.auth_routes import auth_bp
    from app.routes.secrets import secrets_bp
    from app.routes.containers import containers_bp
    from app.routes.orders import orders_bp
    from app.routes.consumers import consumers_bp
    from app.routes.health import health_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(secrets_bp)
    app.register_blueprint(containers_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(consumers_bp)
    app.register_blueprint(health_bp)

    return app

