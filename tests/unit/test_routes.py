"""Unit tests for route handlers."""

import responses
from tests.conftest import SAMPLE_SECRET, SAMPLE_CONTAINER, SAMPLE_ORDER


def test_index_redirects_to_login(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_login_page(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b"Sign in" in resp.data or b"Sign In" in resp.data


@responses.activate
def test_login_success(client):
    responses.add(
        responses.POST,
        "http://keystone.test/v3/auth/tokens",
        json={
            "token": {
                "expires_at": "2099-12-31T23:59:59.000000Z",
                "project": {"id": "p1", "name": "proj"},
                "user": {"id": "u1", "name": "testuser"},
                "catalog": [
                    {"type": "key-manager", "endpoints": [
                        {"interface": "public", "url": "http://barbican.test/", "region": "R1"}
                    ]}
                ],
            }
        },
        headers={"X-Subject-Token": "tok-abc"},
        status=201,
    )
    resp = client.post("/login", data={
        "username": "testuser", "password": "pass", "tenant_value": "proj",
        "tenant_type": "name", "user_domain_name": "Default", "project_domain_name": "Default",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "/secrets" in resp.headers["Location"]


@responses.activate
def test_login_failure(client):
    responses.add(
        responses.POST,
        "http://keystone.test/v3/auth/tokens",
        json={"error": {"message": "Invalid", "code": 401}},
        status=401,
    )
    resp = client.post("/login", data={
        "username": "bad", "password": "bad", "tenant_value": "proj", "tenant_type": "name",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_logout(auth_session):
    resp = auth_session.get("/logout", follow_redirects=False)
    assert resp.status_code == 302


# ── Secrets routes ──────────────────────────────────────────────────

@responses.activate
def test_secrets_list(auth_session):
    responses.add(
        responses.GET, "http://barbican.test/v1/secrets",
        json={"secrets": [SAMPLE_SECRET], "total": 1},
    )
    resp = auth_session.get("/secrets/")
    assert resp.status_code == 200
    assert b"test-secret" in resp.data


@responses.activate
def test_secrets_create_page(auth_session):
    resp = auth_session.get("/secrets/create")
    assert resp.status_code == 200
    assert b"Create Secret" in resp.data


@responses.activate
def test_secrets_create_post(auth_session):
    responses.add(
        responses.POST, "http://barbican.test/v1/secrets",
        json={"secret_ref": "http://barbican.test/v1/secrets/new-id"},
        status=201,
    )
    resp = auth_session.post("/secrets/create", data={
        "name": "new", "secret_type": "opaque", "payload_mode": "simple",
        "payload": "hello", "payload_content_type": "text/plain",
    }, follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_secrets_detail(auth_session):
    responses.add(responses.GET, "http://barbican.test/v1/secrets/s1", json=SAMPLE_SECRET)
    responses.add(responses.GET, "http://barbican.test/v1/secrets/s1/payload", body="secret-val")
    resp = auth_session.get("/secrets/s1")
    assert resp.status_code == 200


@responses.activate
def test_secrets_delete(auth_session):
    responses.add(responses.DELETE, "http://barbican.test/v1/secrets/s1", status=204)
    resp = auth_session.post("/secrets/s1/delete", follow_redirects=False)
    assert resp.status_code == 302


# ── Container routes ────────────────────────────────────────────────

@responses.activate
def test_containers_list(auth_session):
    responses.add(
        responses.GET, "http://barbican.test/v1/containers",
        json={"containers": [SAMPLE_CONTAINER], "total": 1},
    )
    resp = auth_session.get("/containers/")
    assert resp.status_code == 200


@responses.activate
def test_containers_detail(auth_session):
    responses.add(responses.GET, "http://barbican.test/v1/containers/c1", json=SAMPLE_CONTAINER)
    responses.add(responses.GET, "http://barbican.test/v1/containers/c1/consumers", json={"consumers": [], "total": 0})
    resp = auth_session.get("/containers/c1")
    assert resp.status_code == 200


# ── Order routes ────────────────────────────────────────────────────

@responses.activate
def test_orders_list(auth_session):
    responses.add(
        responses.GET, "http://barbican.test/v1/orders",
        json={"orders": [SAMPLE_ORDER], "total": 1},
    )
    resp = auth_session.get("/orders/")
    assert resp.status_code == 200


@responses.activate
def test_orders_detail(auth_session):
    responses.add(responses.GET, "http://barbican.test/v1/orders/o1", json=SAMPLE_ORDER)
    resp = auth_session.get("/orders/o1")
    assert resp.status_code == 200


# ── Health ──────────────────────────────────────────────────────────

def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"


def test_readyz(client):
    resp = client.get("/readyz")
    assert resp.status_code == 200

