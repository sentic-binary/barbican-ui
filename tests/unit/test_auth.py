"""Unit tests for app.auth module."""

import pytest
import requests
import responses

from app.auth import authenticate, AuthError, _normalize_endpoint
from app.config import Config


KEYSTONE_URL = "http://keystone.test/v3"


@pytest.fixture(autouse=True)
def _reload_config():
    """Ensure Config is loaded from env before each test."""
    Config._load()
    yield
    Config._load()


@responses.activate
def test_authenticate_success():
    responses.add(
        responses.POST,
        f"{KEYSTONE_URL}/auth/tokens",
        json={
            "token": {
                "expires_at": "2099-12-31T23:59:59.000000Z",
                "project": {"id": "p1", "name": "proj"},
                "user": {"id": "u1", "name": "admin"},
                "catalog": [
                    {
                        "type": "key-manager",
                        "endpoints": [
                            {"interface": "public", "url": "http://barbican.test/", "region": "R1"}
                        ],
                    }
                ],
            }
        },
        headers={"X-Subject-Token": "tok-123"},
        status=201,
    )

    token = authenticate("admin", "pass", project_name="proj")
    assert token.token == "tok-123"
    assert token.project_id == "p1"
    assert token.user_name == "admin"
    assert not token.is_expired


@responses.activate
def test_authenticate_failure():
    responses.add(
        responses.POST,
        f"{KEYSTONE_URL}/auth/tokens",
        json={"error": {"message": "Invalid credentials", "code": 401}},
        status=401,
    )

    with pytest.raises(AuthError, match="Authentication failed"):
        authenticate("bad", "creds", project_name="proj")


@responses.activate
def test_authenticate_connection_error():
    responses.add(
        responses.POST,
        f"{KEYSTONE_URL}/auth/tokens",
        body=requests.ConnectionError("refused"),
    )

    with pytest.raises(AuthError, match="Cannot connect"):
        authenticate("user", "pass", project_name="proj")


def test_normalize_endpoint_strips_v1():
    assert _normalize_endpoint("https://barbican.test/v1") == "https://barbican.test"
    assert _normalize_endpoint("https://barbican.test/v1/") == "https://barbican.test"


def test_normalize_endpoint_no_version():
    assert _normalize_endpoint("https://barbican.test") == "https://barbican.test"
    assert _normalize_endpoint("https://barbican.test/") == "https://barbican.test"


@responses.activate
def test_authenticate_catalog_with_v1_endpoint(monkeypatch):
    """Endpoint URLs containing /v1 should be normalized."""
    monkeypatch.setenv("OS_BARBICAN_ENDPOINT", "")
    monkeypatch.setenv("BARBICAN_ENDPOINT_AUTODISCOVERY", "true")
    from app.config import Config
    Config._load()
    responses.add(
        responses.POST,
        f"{KEYSTONE_URL}/auth/tokens",
        json={
            "token": {
                "expires_at": "2099-12-31T23:59:59.000000Z",
                "project": {"id": "p1", "name": "proj"},
                "user": {"id": "u1", "name": "admin"},
                "catalog": [
                    {
                        "type": "key-manager",
                        "endpoints": [
                            {"interface": "public", "url": "https://key-manager.bhs.cloud.ovh.net/v1/", "region": "R1"}
                        ],
                    }
                ],
            }
        },
        headers={"X-Subject-Token": "tok-456"},
        status=201,
    )

    token = authenticate("admin", "pass", project_name="proj")
    assert token.barbican_endpoint == "https://key-manager.bhs.cloud.ovh.net"


