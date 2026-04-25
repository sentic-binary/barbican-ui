"""Barbican UI – Configuration module.

All settings are loaded from environment variables with sensible defaults.
"""

import os
import sys


class Config:
    """Application configuration loaded exclusively from environment variables."""

    # --- Keystone -----------------------------------------------------------
    OS_AUTH_URL: str = ""
    OS_IDENTITY_API_VERSION: str = "3"
    OS_USER_DOMAIN_NAME: str = "Default"
    OS_PROJECT_DOMAIN_NAME: str = "Default"
    OS_REGION_NAME: str = ""
    OS_TENANT_ID: str = ""
    OS_TENANT_NAME: str = ""

    # --- Barbican ------------------------------------------------------------
    BARBICAN_ENDPOINT_AUTODISCOVERY: bool = True
    OS_BARBICAN_ENDPOINT: str = ""

    # --- Application ---------------------------------------------------------
    SECRET_KEY: str = "change-me"
    SESSION_LIFETIME_SECONDS: int = 3600
    SESSION_COOKIE_SECURE: bool = True
    SESSION_BIND_IP: bool = True
    CACHE_TTL_SECONDS: int = 300
    CACHE_DIR: str = "/tmp/barbican-ui-cache"
    LOG_LEVEL: str = "INFO"
    FLASK_PORT: int = 8080

    @classmethod
    def _load(cls) -> None:
        """Re-read all values from environment (call after load_dotenv)."""
        cls.OS_AUTH_URL = os.environ.get("OS_AUTH_URL", "")
        cls.OS_IDENTITY_API_VERSION = os.environ.get("OS_IDENTITY_API_VERSION", "3")
        cls.OS_USER_DOMAIN_NAME = os.environ.get("OS_USER_DOMAIN_NAME", "Default")
        cls.OS_PROJECT_DOMAIN_NAME = os.environ.get("OS_PROJECT_DOMAIN_NAME", "Default")
        cls.OS_REGION_NAME = os.environ.get("OS_REGION_NAME", "")
        cls.OS_TENANT_ID = os.environ.get("OS_TENANT_ID", "")
        cls.OS_TENANT_NAME = os.environ.get("OS_TENANT_NAME", "")
        cls.BARBICAN_ENDPOINT_AUTODISCOVERY = (
            os.environ.get("BARBICAN_ENDPOINT_AUTODISCOVERY", "true").lower() == "true"
        )
        cls.OS_BARBICAN_ENDPOINT = os.environ.get("OS_BARBICAN_ENDPOINT", "")
        cls.SECRET_KEY = os.environ.get("SECRET_KEY", "change-me")
        cls.SESSION_LIFETIME_SECONDS = int(os.environ.get("SESSION_LIFETIME_SECONDS", "3600"))
        cls.SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() == "true"
        cls.SESSION_BIND_IP = os.environ.get("SESSION_BIND_IP", "true").lower() == "true"
        cls.CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "300"))
        cls.CACHE_DIR = os.environ.get("CACHE_DIR", "/tmp/barbican-ui-cache")
        cls.LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
        cls.FLASK_PORT = int(os.environ.get("FLASK_PORT", "8080"))

    @classmethod
    def validate(cls) -> None:
        """Load from env and validate required configuration. Exits on failure."""
        cls._load()

        errors: list[str] = []

        if not cls.OS_AUTH_URL:
            errors.append("OS_AUTH_URL is required (e.g. https://keystone.example.com/v3)")

        if not cls.BARBICAN_ENDPOINT_AUTODISCOVERY and not cls.OS_BARBICAN_ENDPOINT:
            errors.append(
                "OS_BARBICAN_ENDPOINT is required when "
                "BARBICAN_ENDPOINT_AUTODISCOVERY=false"
            )

        if cls.SECRET_KEY == "change-me":
            import warnings
            warnings.warn(
                "SECRET_KEY is set to the default value. "
                "Set a strong random secret for production use.",
                stacklevel=2,
            )

        if errors:
            for e in errors:
                print(f"[CONFIG ERROR] {e}", file=sys.stderr)
            sys.exit(1)

