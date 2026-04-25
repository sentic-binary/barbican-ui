"""Barbican UI – Configuration module.

All settings are loaded from environment variables with sensible defaults.
"""

import os
import sys


class Config:
    """Application configuration loaded exclusively from environment variables."""

    # --- Keystone -----------------------------------------------------------
    OS_AUTH_URL: str = os.environ.get("OS_AUTH_URL", "")
    OS_IDENTITY_API_VERSION: str = os.environ.get("OS_IDENTITY_API_VERSION", "3")
    OS_USER_DOMAIN_NAME: str = os.environ.get("OS_USER_DOMAIN_NAME", "Default")
    OS_PROJECT_DOMAIN_NAME: str = os.environ.get("OS_PROJECT_DOMAIN_NAME", "Default")
    OS_REGION_NAME: str = os.environ.get("OS_REGION_NAME", "")
    OS_TENANT_ID: str = os.environ.get("OS_TENANT_ID", "")
    OS_TENANT_NAME: str = os.environ.get("OS_TENANT_NAME", "")

    # --- Barbican ------------------------------------------------------------
    BARBICAN_ENDPOINT_AUTODISCOVERY: bool = (
        os.environ.get("BARBICAN_ENDPOINT_AUTODISCOVERY", "true").lower() == "true"
    )
    OS_BARBICAN_ENDPOINT: str = os.environ.get("OS_BARBICAN_ENDPOINT", "")

    # --- Application ---------------------------------------------------------
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "change-me")
    SESSION_LIFETIME_SECONDS: int = int(
        os.environ.get("SESSION_LIFETIME_SECONDS", "3600")
    )
    CACHE_TTL_SECONDS: int = int(os.environ.get("CACHE_TTL_SECONDS", "300"))
    CACHE_DIR: str = os.environ.get("CACHE_DIR", "/tmp/barbican-ui-cache")
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
    FLASK_PORT: int = int(os.environ.get("FLASK_PORT", "8080"))

    @classmethod
    def validate(cls) -> None:
        """Validate required configuration at startup. Exits on failure."""
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

