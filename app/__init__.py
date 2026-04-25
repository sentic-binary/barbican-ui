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
    app.config["SESSION_COOKIE_SECURE"] = Config.SESSION_COOKIE_SECURE
    app.config["SESSION_COOKIE_NAME"] = "barbican_ui_session"
    app.config["PERMANENT_SESSION_LIFETIME"] = Config.SESSION_LIFETIME_SECONDS
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB upload limit

    # Server-side filesystem sessions (flask-session)
    import os as _os
    session_dir = _os.path.join(Config.CACHE_DIR, "sessions")
    _os.makedirs(session_dir, mode=0o700, exist_ok=True)

    from cachelib.file import FileSystemCache
    app.config["SESSION_TYPE"] = "cachelib"
    app.config["SESSION_CACHELIB"] = FileSystemCache(
        cache_dir=session_dir,
        threshold=500,
    )
    app.config["SESSION_PERMANENT"] = True

    from flask_session import Session
    Session(app)

    # CSRF protection (flask-wtf)
    from flask_wtf.csrf import CSRFProtect

    csrf = CSRFProtect(app)
    app.config["WTF_CSRF_ENABLED"] = not testing
    # Exempt health endpoints from CSRF
    csrf.exempt("health.healthz")
    csrf.exempt("health.readyz")

    # Logging
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Security headers
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if Config.SESSION_COOKIE_SECURE:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        return response

    # Register blueprints
    from app.routes.auth_routes import auth_bp
    from app.routes.secrets import secrets_bp
    from app.routes.containers import containers_bp
    from app.routes.orders import orders_bp
    from app.routes.consumers import consumers_bp
    from app.routes.health import health_bp
    from app.routes.docs import docs_bp
    from app.routes.transfer import transfer_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(secrets_bp)
    app.register_blueprint(containers_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(consumers_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(docs_bp)
    app.register_blueprint(transfer_bp)

    return app

