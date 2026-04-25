"""Unit tests for app.config module."""

import os
import pytest


class TestConfigLoad:
    """Test Config._load() with various environment variables."""

    def test_defaults(self, monkeypatch):
        monkeypatch.setenv("OS_AUTH_URL", "http://keystone.test/v3")
        monkeypatch.setenv("SECRET_KEY", "test-key-not-default")
        monkeypatch.delenv("OS_REGION_NAME", raising=False)
        monkeypatch.delenv("OS_TENANT_NAME", raising=False)
        monkeypatch.delenv("OS_TENANT_ID", raising=False)
        monkeypatch.delenv("BARBICAN_ENDPOINT_AUTODISCOVERY", raising=False)
        monkeypatch.delenv("OS_BARBICAN_ENDPOINT", raising=False)
        monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
        monkeypatch.delenv("SESSION_BIND_IP", raising=False)
        monkeypatch.delenv("CACHE_DIR", raising=False)
        monkeypatch.setenv("BARBICAN_ENDPOINT_AUTODISCOVERY", "false")
        monkeypatch.setenv("OS_BARBICAN_ENDPOINT", "http://barbican.test")

        from app.config import Config
        Config._load()

        assert Config.OS_IDENTITY_API_VERSION == "3"
        assert Config.OS_USER_DOMAIN_NAME == "Default"
        assert Config.OS_PROJECT_DOMAIN_NAME == "Default"
        assert Config.SESSION_LIFETIME_SECONDS == 3600
        assert Config.SESSION_COOKIE_SECURE is True
        assert Config.SESSION_BIND_IP is True
        assert Config.CACHE_TTL_SECONDS == 300
        assert Config.CACHE_DIR == "/tmp/barbican-ui-cache"
        assert Config.LOG_LEVEL == "INFO"
        assert Config.FLASK_PORT == 8080

    def test_custom_values(self, monkeypatch):
        monkeypatch.setenv("OS_AUTH_URL", "http://custom/v3")
        monkeypatch.setenv("SECRET_KEY", "custom-key")
        monkeypatch.setenv("OS_REGION_NAME", "GRA")
        monkeypatch.setenv("OS_TENANT_NAME", "myproject")
        monkeypatch.setenv("SESSION_LIFETIME_SECONDS", "7200")
        monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
        monkeypatch.setenv("SESSION_BIND_IP", "false")
        monkeypatch.setenv("CACHE_TTL_SECONDS", "600")
        monkeypatch.setenv("CACHE_DIR", "/data/cache")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("FLASK_PORT", "9090")
        monkeypatch.setenv("BARBICAN_ENDPOINT_AUTODISCOVERY", "false")
        monkeypatch.setenv("OS_BARBICAN_ENDPOINT", "http://barbican.test")

        from app.config import Config
        Config._load()

        assert Config.OS_AUTH_URL == "http://custom/v3"
        assert Config.OS_REGION_NAME == "GRA"
        assert Config.OS_TENANT_NAME == "myproject"
        assert Config.SESSION_LIFETIME_SECONDS == 7200
        assert Config.SESSION_COOKIE_SECURE is False
        assert Config.SESSION_BIND_IP is False
        assert Config.CACHE_TTL_SECONDS == 600
        assert Config.CACHE_DIR == "/data/cache"
        assert Config.LOG_LEVEL == "DEBUG"
        assert Config.FLASK_PORT == 9090

    def test_invalid_int_values_use_defaults(self, monkeypatch):
        monkeypatch.setenv("OS_AUTH_URL", "http://keystone.test/v3")
        monkeypatch.setenv("SECRET_KEY", "test-key-not-default")
        monkeypatch.setenv("SESSION_LIFETIME_SECONDS", "not-a-number")
        monkeypatch.setenv("CACHE_TTL_SECONDS", "bad")
        monkeypatch.setenv("FLASK_PORT", "abc")
        monkeypatch.setenv("BARBICAN_ENDPOINT_AUTODISCOVERY", "false")
        monkeypatch.setenv("OS_BARBICAN_ENDPOINT", "http://barbican.test")

        from app.config import Config
        Config._load()

        assert Config.SESSION_LIFETIME_SECONDS == 3600
        assert Config.CACHE_TTL_SECONDS == 300
        assert Config.FLASK_PORT == 8080

    def test_barbican_autodiscovery_true(self, monkeypatch):
        monkeypatch.setenv("BARBICAN_ENDPOINT_AUTODISCOVERY", "true")
        from app.config import Config
        Config._load()
        assert Config.BARBICAN_ENDPOINT_AUTODISCOVERY is True

    def test_barbican_autodiscovery_false(self, monkeypatch):
        monkeypatch.setenv("BARBICAN_ENDPOINT_AUTODISCOVERY", "false")
        from app.config import Config
        Config._load()
        assert Config.BARBICAN_ENDPOINT_AUTODISCOVERY is False

    def test_barbican_autodiscovery_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("BARBICAN_ENDPOINT_AUTODISCOVERY", "TRUE")
        from app.config import Config
        Config._load()
        assert Config.BARBICAN_ENDPOINT_AUTODISCOVERY is True


class TestConfigTlsVerify:
    def test_returns_true_without_cacert(self, monkeypatch):
        monkeypatch.setenv("OS_CACERT", "")
        from app.config import Config
        Config._load()
        assert Config.tls_verify() is True

    def test_returns_path_with_cacert(self, monkeypatch):
        monkeypatch.setenv("OS_CACERT", "/etc/ssl/custom-ca.pem")
        from app.config import Config
        Config._load()
        assert Config.tls_verify() == "/etc/ssl/custom-ca.pem"


class TestConfigValidate:
    def test_missing_auth_url_exits(self, monkeypatch):
        monkeypatch.setenv("OS_AUTH_URL", "")
        monkeypatch.setenv("SECRET_KEY", "good-key")
        monkeypatch.setenv("BARBICAN_ENDPOINT_AUTODISCOVERY", "true")

        from app.config import Config
        with pytest.raises(SystemExit):
            Config.validate()

    def test_missing_barbican_endpoint_when_no_autodiscovery(self, monkeypatch):
        monkeypatch.setenv("OS_AUTH_URL", "http://keystone.test/v3")
        monkeypatch.setenv("SECRET_KEY", "good-key")
        monkeypatch.setenv("BARBICAN_ENDPOINT_AUTODISCOVERY", "false")
        monkeypatch.setenv("OS_BARBICAN_ENDPOINT", "")

        from app.config import Config
        with pytest.raises(SystemExit):
            Config.validate()

    def test_default_secret_key_exits(self, monkeypatch):
        monkeypatch.setenv("OS_AUTH_URL", "http://keystone.test/v3")
        monkeypatch.setenv("SECRET_KEY", "change-me")
        monkeypatch.setenv("BARBICAN_ENDPOINT_AUTODISCOVERY", "true")

        from app.config import Config
        with pytest.raises(SystemExit):
            Config.validate()



