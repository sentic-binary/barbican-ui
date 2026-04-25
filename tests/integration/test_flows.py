"""Integration tests – full flow through fake Keystone + Barbican servers."""

import json
import pytest
import responses

from app.cache import get_cache


@pytest.fixture(autouse=True)
def clear_cache():
    get_cache().clear()
    yield
    get_cache().clear()


KEYSTONE = "http://keystone.test/v3"
BARBICAN = "http://barbican.test"


def _mock_keystone_auth():
    responses.add(
        responses.POST,
        f"{KEYSTONE}/auth/tokens",
        json={
            "token": {
                "expires_at": "2099-12-31T23:59:59.000000Z",
                "project": {"id": "p1", "name": "proj"},
                "user": {"id": "u1", "name": "admin"},
                "catalog": [
                    {"type": "key-manager", "endpoints": [
                        {"interface": "public", "url": f"{BARBICAN}/", "region": "R1"}
                    ]}
                ],
            }
        },
        headers={"X-Subject-Token": "tok-int"},
        status=201,
    )


@responses.activate
def test_full_secret_lifecycle(client):
    """Login → create secret → list → get → delete → logout."""
    _mock_keystone_auth()

    # Login
    resp = client.post("/login", data={
        "username": "admin", "password": "pass", "tenant_value": "proj", "tenant_type": "name",
    }, follow_redirects=False)
    assert resp.status_code == 302

    # Store secret
    responses.add(
        responses.POST, f"{BARBICAN}/v1/secrets",
        json={"secret_ref": f"{BARBICAN}/v1/secrets/int-s1"}, status=201,
    )
    resp = client.post("/secrets/create", data={
        "name": "int-secret", "secret_type": "opaque",
        "payload_mode": "kv", "kv_key": ["db_host", "db_pass"], "kv_value": ["localhost", "s3cret"],
    }, follow_redirects=False)
    assert resp.status_code == 302

    # List
    responses.add(
        responses.GET, f"{BARBICAN}/v1/secrets",
        json={"secrets": [{"secret_ref": f"{BARBICAN}/v1/secrets/int-s1", "name": "int-secret",
                           "status": "ACTIVE", "secret_type": "opaque", "algorithm": None,
                           "created": "2026-01-01T00:00:00"}], "total": 1},
    )
    resp = client.get("/secrets/")
    assert resp.status_code == 200
    assert b"int-secret" in resp.data

    # Get detail
    responses.add(
        responses.GET, f"{BARBICAN}/v1/secrets/int-s1",
        json={"name": "int-secret", "status": "ACTIVE", "secret_type": "opaque",
              "content_types": {"default": "text/plain"}, "created": "2026-01-01T00:00:00",
              "algorithm": None, "bit_length": None, "mode": None, "updated": None, "expiration": None},
    )
    responses.add(
        responses.GET, f"{BARBICAN}/v1/secrets/int-s1/payload",
        body='{"db_host": "localhost", "db_pass": "s3cret"}',
    )
    resp = client.get("/secrets/int-s1")
    assert resp.status_code == 200
    assert b"db_host" in resp.data

    # Delete
    responses.add(responses.DELETE, f"{BARBICAN}/v1/secrets/int-s1", status=204)
    resp = client.post("/secrets/int-s1/delete", follow_redirects=False)
    assert resp.status_code == 302

    # Logout
    resp = client.post("/logout", follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_full_container_lifecycle(client):
    """Login → create container → get → add consumer → delete consumer → delete container."""
    _mock_keystone_auth()

    # Login
    client.post("/login", data={
        "username": "admin", "password": "pass", "tenant_value": "proj", "tenant_type": "name",
    })

    # Create container
    responses.add(
        responses.GET, f"{BARBICAN}/v1/secrets",
        json={"secrets": [], "total": 0},
    )
    responses.add(
        responses.POST, f"{BARBICAN}/v1/containers",
        json={"container_ref": f"{BARBICAN}/v1/containers/int-c1"}, status=201,
    )
    resp = client.post("/containers/create", data={
        "name": "int-ctr", "type": "generic", "ref_name": [], "ref_id": [],
    }, follow_redirects=False)
    assert resp.status_code == 302

    # Get
    responses.add(
        responses.GET, f"{BARBICAN}/v1/containers/int-c1",
        json={"name": "int-ctr", "type": "generic", "secret_refs": [],
              "created": "2026-01-01T00:00:00", "updated": None},
    )
    responses.add(
        responses.GET, f"{BARBICAN}/v1/containers/int-c1/consumers",
        json={"consumers": [], "total": 0},
    )
    resp = client.get("/containers/int-c1")
    assert resp.status_code == 200

    # Register consumer
    responses.add(
        responses.POST, f"{BARBICAN}/v1/containers/int-c1/consumers",
        json={"name": "myapp", "URL": "http://myapp.example.com"}, status=200,
    )
    resp = client.post("/consumers/int-c1/create", data={
        "name": "myapp", "url": "http://myapp.example.com",
    }, follow_redirects=False)
    assert resp.status_code == 302

    # Delete consumer
    responses.add(responses.DELETE, f"{BARBICAN}/v1/containers/int-c1/consumers", status=204)
    resp = client.post("/consumers/int-c1/delete", data={
        "name": "myapp", "url": "http://myapp.example.com",
    }, follow_redirects=False)
    assert resp.status_code == 302

    # Delete container
    responses.add(responses.DELETE, f"{BARBICAN}/v1/containers/int-c1", status=204)
    resp = client.post("/containers/int-c1/delete", follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_full_order_lifecycle(client):
    """Login → create order → get → delete."""
    _mock_keystone_auth()
    client.post("/login", data={
        "username": "admin", "password": "pass", "tenant_value": "proj", "tenant_type": "name",
    })

    # Create
    responses.add(
        responses.POST, f"{BARBICAN}/v1/orders",
        json={"order_ref": f"{BARBICAN}/v1/orders/int-o1"}, status=202,
    )
    resp = client.post("/orders/create", data={
        "type": "key", "name": "mykey", "algorithm": "aes",
        "bit_length": "256", "mode": "cbc",
        "payload_content_type": "application/octet-stream",
    }, follow_redirects=False)
    assert resp.status_code == 302

    # Get
    responses.add(
        responses.GET, f"{BARBICAN}/v1/orders/int-o1",
        json={"type": "key", "status": "ACTIVE", "meta": {"name": "mykey"},
              "created": "2026-01-01", "updated": None, "order_ref": f"{BARBICAN}/v1/orders/int-o1",
              "secret_ref": f"{BARBICAN}/v1/secrets/gen-s1"},
    )
    resp = client.get("/orders/int-o1")
    assert resp.status_code == 200

    # Delete
    responses.add(responses.DELETE, f"{BARBICAN}/v1/orders/int-o1", status=204)
    resp = client.post("/orders/int-o1/delete", follow_redirects=False)
    assert resp.status_code == 302

