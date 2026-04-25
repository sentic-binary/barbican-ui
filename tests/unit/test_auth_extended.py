"""Extended tests for app.auth module — endpoint resolution edge cases."""

import pytest
import responses

from app.auth import authenticate, AuthError, AuthToken, _normalize_endpoint, _resolve_barbican_endpoint
from app.config import Config


class TestNormalizeEndpoint:
    def test_strips_v1(self):
        assert _normalize_endpoint("https://bar.test/v1") == "https://bar.test"

    def test_strips_v1_trailing_slash(self):
        assert _normalize_endpoint("https://bar.test/v1/") == "https://bar.test"

    def test_strips_v2(self):
        assert _normalize_endpoint("https://bar.test/v2") == "https://bar.test"

    def test_strips_v1_0(self):
        assert _normalize_endpoint("https://bar.test/v1.0") == "https://bar.test"

    def test_no_version(self):
        assert _normalize_endpoint("https://bar.test") == "https://bar.test"

    def test_trailing_slash_only(self):
        assert _normalize_endpoint("https://bar.test/") == "https://bar.test"


class TestResolveBarbicanEndpoint:
    def test_explicit_override_wins(self, monkeypatch):
        monkeypatch.setenv("OS_BARBICAN_ENDPOINT", "https://explicit.test/v1")
        Config._load()
        result = _resolve_barbican_endpoint([], "R1")
        assert result == "https://explicit.test"

    def test_autodiscovery_with_region(self, monkeypatch):
        monkeypatch.setenv("OS_BARBICAN_ENDPOINT", "")
        monkeypatch.setenv("BARBICAN_ENDPOINT_AUTODISCOVERY", "true")
        Config._load()
        catalog = [{
            "type": "key-manager",
            "endpoints": [
                {"interface": "public", "url": "https://r1.test/v1", "region": "R1"},
                {"interface": "public", "url": "https://r2.test/v1", "region": "R2"},
            ],
        }]
        assert _resolve_barbican_endpoint(catalog, "R2") == "https://r2.test"

    def test_autodiscovery_fallback_first_public(self, monkeypatch):
        monkeypatch.setenv("OS_BARBICAN_ENDPOINT", "")
        monkeypatch.setenv("BARBICAN_ENDPOINT_AUTODISCOVERY", "true")
        Config._load()
        catalog = [{
            "type": "key-manager",
            "endpoints": [
                {"interface": "public", "url": "https://first.test/v1", "region": "R1"},
            ],
        }]
        assert _resolve_barbican_endpoint(catalog, "MISSING") == "https://first.test"

    def test_autodiscovery_no_region_takes_first(self, monkeypatch):
        monkeypatch.setenv("OS_BARBICAN_ENDPOINT", "")
        monkeypatch.setenv("BARBICAN_ENDPOINT_AUTODISCOVERY", "true")
        Config._load()
        catalog = [{
            "type": "key-manager",
            "endpoints": [
                {"interface": "public", "url": "https://any.test/", "region": "X"},
            ],
        }]
        assert _resolve_barbican_endpoint(catalog, "") == "https://any.test"

    def test_no_key_manager_returns_empty(self, monkeypatch):
        monkeypatch.setenv("OS_BARBICAN_ENDPOINT", "")
        monkeypatch.setenv("BARBICAN_ENDPOINT_AUTODISCOVERY", "true")
        Config._load()
        catalog = [{"type": "compute", "endpoints": []}]
        assert _resolve_barbican_endpoint(catalog, "") == ""

    def test_autodiscovery_disabled_no_override(self, monkeypatch):
        monkeypatch.setenv("OS_BARBICAN_ENDPOINT", "")
        monkeypatch.setenv("BARBICAN_ENDPOINT_AUTODISCOVERY", "false")
        Config._load()
        assert _resolve_barbican_endpoint([{"type": "key-manager", "endpoints": [{"interface": "public", "url": "https://x.test"}]}], "") == ""

    def test_region_id_match(self, monkeypatch):
        monkeypatch.setenv("OS_BARBICAN_ENDPOINT", "")
        monkeypatch.setenv("BARBICAN_ENDPOINT_AUTODISCOVERY", "true")
        Config._load()
        catalog = [{
            "type": "key-manager",
            "endpoints": [
                {"interface": "public", "url": "https://r1.test/", "region_id": "R1"},
            ],
        }]
        assert _resolve_barbican_endpoint(catalog, "R1") == "https://r1.test"


class TestAuthToken:
    def test_is_expired_future(self):
        from datetime import datetime, timezone
        t = AuthToken("t", datetime(2099, 1, 1, tzinfo=timezone.utc), "p", "pn", "u", "un", "ep", [])
        assert not t.is_expired

    def test_is_expired_past(self):
        from datetime import datetime, timezone
        t = AuthToken("t", datetime(2020, 1, 1, tzinfo=timezone.utc), "p", "pn", "u", "un", "ep", [])
        assert t.is_expired


@responses.activate
def test_authenticate_with_project_id():
    responses.add(
        responses.POST, "http://keystone.test/v3/auth/tokens",
        json={
            "token": {
                "expires_at": "2099-12-31T23:59:59.000000Z",
                "project": {"id": "p1", "name": "proj"},
                "user": {"id": "u1", "name": "admin"},
                "catalog": [{"type": "key-manager", "endpoints": [
                    {"interface": "public", "url": "http://barbican.test/", "region": "R1"}
                ]}],
            }
        },
        headers={"X-Subject-Token": "tok-pid"},
        status=201,
    )
    token = authenticate("admin", "pass", project_id="p1")
    assert token.token == "tok-pid"


@responses.activate
def test_authenticate_no_scope():
    """Auth without project name or ID should still work (unscoped)."""
    responses.add(
        responses.POST, "http://keystone.test/v3/auth/tokens",
        json={
            "token": {
                "expires_at": "2099-12-31T23:59:59.000000Z",
                "project": {},
                "user": {"id": "u1", "name": "admin"},
                "catalog": [],
            }
        },
        headers={"X-Subject-Token": "tok-unscoped"},
        status=201,
    )
    # Clear tenant config
    import os
    old_name = os.environ.get("OS_TENANT_NAME", "")
    old_id = os.environ.get("OS_TENANT_ID", "")
    os.environ["OS_TENANT_NAME"] = ""
    os.environ["OS_TENANT_ID"] = ""
    Config._load()

    token = authenticate("admin", "pass")
    assert token.token == "tok-unscoped"

    os.environ["OS_TENANT_NAME"] = old_name
    os.environ["OS_TENANT_ID"] = old_id
    Config._load()


@responses.activate
def test_authenticate_bad_expires_at():
    """Invalid expires_at should default to now."""
    responses.add(
        responses.POST, "http://keystone.test/v3/auth/tokens",
        json={
            "token": {
                "expires_at": "not-a-date",
                "project": {"id": "p1", "name": "proj"},
                "user": {"id": "u1", "name": "admin"},
                "catalog": [{"type": "key-manager", "endpoints": [
                    {"interface": "public", "url": "http://barbican.test/", "region": "R1"}
                ]}],
            }
        },
        headers={"X-Subject-Token": "tok-bad-date"},
        status=201,
    )
    token = authenticate("admin", "pass", project_name="proj")
    assert token.token == "tok-bad-date"
    # Should be expired since it defaults to now
    assert token.is_expired

