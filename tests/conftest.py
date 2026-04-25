"""Shared test fixtures."""

import os
import pytest

# Set required env vars before importing app
os.environ.setdefault("OS_AUTH_URL", "http://keystone.test/v3")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only")
os.environ.setdefault("CACHE_DIR", "/tmp/barbican-ui-test-cache")
os.environ.setdefault("BARBICAN_ENDPOINT_AUTODISCOVERY", "false")
os.environ.setdefault("OS_BARBICAN_ENDPOINT", "http://barbican.test")

from app import create_app


SAMPLE_TOKEN_RESPONSE = {
    "token": {
        "expires_at": "2099-12-31T23:59:59.000000Z",
        "project": {"id": "proj123", "name": "myproject"},
        "user": {"id": "user456", "name": "testuser"},
        "catalog": [
            {
                "type": "key-manager",
                "endpoints": [
                    {
                        "interface": "public",
                        "url": "http://barbican.test/",
                        "region": "RegionOne",
                    }
                ],
            }
        ],
    }
}

SAMPLE_SECRET = {
    "secret_ref": "http://barbican.test/v1/secrets/sec-uuid-1",
    "name": "test-secret",
    "status": "ACTIVE",
    "secret_type": "opaque",
    "algorithm": None,
    "bit_length": None,
    "mode": None,
    "created": "2026-01-01T00:00:00",
    "updated": None,
    "expiration": None,
    "content_types": {"default": "text/plain"},
}

SAMPLE_CONTAINER = {
    "container_ref": "http://barbican.test/v1/containers/ctr-uuid-1",
    "name": "test-container",
    "type": "generic",
    "secret_refs": [],
    "created": "2026-01-01T00:00:00",
    "updated": None,
}

SAMPLE_ORDER = {
    "order_ref": "http://barbican.test/v1/orders/ord-uuid-1",
    "type": "key",
    "status": "ACTIVE",
    "meta": {"name": "test-key", "algorithm": "aes", "bit_length": 256},
    "created": "2026-01-01T00:00:00",
    "updated": None,
    "secret_ref": "http://barbican.test/v1/secrets/sec-uuid-2",
}


@pytest.fixture
def app():
    application = create_app(testing=True)
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_session(client):
    """Return a client with a valid session pre-populated."""
    with client.session_transaction() as sess:
        sess["auth"] = {
            "token": "fake-token-abc",
            "expires_at": "2099-12-31T23:59:59+00:00",
            "project_id": "proj123",
            "project_name": "myproject",
            "user_id": "user456",
            "user_name": "testuser",
            "barbican_endpoint": "http://barbican.test",
            "catalog": [],
        }
    return client

