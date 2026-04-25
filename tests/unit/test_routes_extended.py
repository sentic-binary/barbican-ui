"""Extended route tests — auth edge cases, transfer, virtual folders, more coverage."""

import io
import json
import time
import responses
import pytest

from app.cache import get_cache
from tests.conftest import SAMPLE_SECRET, SAMPLE_CONTAINER, SAMPLE_ORDER

BARBICAN = "http://barbican.test"


# ── Auth edge cases ─────────────────────────────────────────────────


def test_login_missing_username(client):
    resp = client.post("/login", data={"username": "", "password": "pass", "tenant_value": "proj"}, follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_login_missing_password(client):
    resp = client.post("/login", data={"username": "user", "password": "", "tenant_value": "proj"}, follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


@responses.activate
def test_login_auto_detect_project_id(client):
    """When tenant_type=auto and value is UUID-like, should use project_id."""
    responses.add(
        responses.POST, "http://keystone.test/v3/auth/tokens",
        json={
            "token": {
                "expires_at": "2099-12-31T23:59:59.000000Z",
                "project": {"id": "abc12345678901234567890123456789", "name": "proj"},
                "user": {"id": "u1", "name": "user"},
                "catalog": [{"type": "key-manager", "endpoints": [
                    {"interface": "public", "url": "http://barbican.test/", "region": "R1"}
                ]}],
            }
        },
        headers={"X-Subject-Token": "tok"},
        status=201,
    )
    resp = client.post("/login", data={
        "username": "user", "password": "pass",
        "tenant_value": "abc12345678901234567890123456789",
        "tenant_type": "auto",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "/secrets" in resp.headers["Location"]


@responses.activate
def test_login_no_barbican_endpoint(client):
    """When Barbican endpoint can't be discovered, should flash error."""
    responses.add(
        responses.POST, "http://keystone.test/v3/auth/tokens",
        json={
            "token": {
                "expires_at": "2099-12-31T23:59:59.000000Z",
                "project": {"id": "p1", "name": "proj"},
                "user": {"id": "u1", "name": "user"},
                "catalog": [],  # no key-manager
            }
        },
        headers={"X-Subject-Token": "tok"},
        status=201,
    )
    # Need autodiscovery on and no explicit endpoint
    import os
    old_ep = os.environ.get("OS_BARBICAN_ENDPOINT", "")
    old_ad = os.environ.get("BARBICAN_ENDPOINT_AUTODISCOVERY", "")
    os.environ["OS_BARBICAN_ENDPOINT"] = ""
    os.environ["BARBICAN_ENDPOINT_AUTODISCOVERY"] = "true"
    from app.config import Config
    Config._load()

    resp = client.post("/login", data={
        "username": "user", "password": "pass",
        "tenant_value": "proj", "tenant_type": "name",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

    # Restore
    os.environ["OS_BARBICAN_ENDPOINT"] = old_ep
    os.environ["BARBICAN_ENDPOINT_AUTODISCOVERY"] = old_ad
    Config._load()


def test_unauthenticated_secrets_redirects(client):
    resp = client.get("/secrets/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_unauthenticated_containers_redirects(client):
    resp = client.get("/containers/", follow_redirects=False)
    assert resp.status_code == 302


def test_unauthenticated_orders_redirects(client):
    resp = client.get("/orders/", follow_redirects=False)
    assert resp.status_code == 302


def test_unauthenticated_transfer_redirects(client):
    resp = client.get("/transfer/", follow_redirects=False)
    assert resp.status_code == 302


def test_unauthenticated_docs_redirects(client):
    resp = client.get("/docs", follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_login_tenant_type_id(client):
    """When tenant_type=id explicitly, should use project_id."""
    from app.routes.auth_routes import _login_attempts
    _login_attempts.clear()
    responses.add(
        responses.POST, "http://keystone.test/v3/auth/tokens",
        json={
            "token": {
                "expires_at": "2099-12-31T23:59:59.000000Z",
                "project": {"id": "explicit-id-123", "name": "proj"},
                "user": {"id": "u1", "name": "user"},
                "catalog": [{"type": "key-manager", "endpoints": [
                    {"interface": "public", "url": "http://barbican.test/", "region": "R1"}
                ]}],
            }
        },
        headers={"X-Subject-Token": "tok"},
        status=201,
    )
    resp = client.post("/login", data={
        "username": "user", "password": "pass",
        "tenant_value": "explicit-id-123",
        "tenant_type": "id",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "/secrets" in resp.headers["Location"]


@responses.activate
def test_login_tenant_type_name(client):
    """When tenant_type=name explicitly."""
    from app.routes.auth_routes import _login_attempts
    _login_attempts.clear()
    responses.add(
        responses.POST, "http://keystone.test/v3/auth/tokens",
        json={
            "token": {
                "expires_at": "2099-12-31T23:59:59.000000Z",
                "project": {"id": "p1", "name": "my-project"},
                "user": {"id": "u1", "name": "user"},
                "catalog": [{"type": "key-manager", "endpoints": [
                    {"interface": "public", "url": "http://barbican.test/", "region": "R1"}
                ]}],
            }
        },
        headers={"X-Subject-Token": "tok"},
        status=201,
    )
    resp = client.post("/login", data={
        "username": "user", "password": "pass",
        "tenant_value": "my-project",
        "tenant_type": "name",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "/secrets" in resp.headers["Location"]


def test_index_redirects_to_secrets_when_authenticated(auth_session):
    resp = auth_session.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/secrets" in resp.headers["Location"]


# ── Secrets — virtual folders ───────────────────────────────────────


@responses.activate
def test_secrets_list_with_folder_path(auth_session):
    get_cache().clear()
    responses.add(
        responses.GET, "http://barbican.test/v1/secrets",
        json={
            "secrets": [
                {"secret_ref": "http://barbican.test/v1/secrets/s1", "name": "prod/db/password", "status": "ACTIVE", "secret_type": "opaque"},
                {"secret_ref": "http://barbican.test/v1/secrets/s2", "name": "prod/db/host", "status": "ACTIVE", "secret_type": "opaque"},
                {"secret_ref": "http://barbican.test/v1/secrets/s3", "name": "prod/api/key", "status": "ACTIVE", "secret_type": "opaque"},
                {"secret_ref": "http://barbican.test/v1/secrets/s4", "name": "staging/db/password", "status": "ACTIVE", "secret_type": "opaque"},
            ],
            "total": 4,
        },
    )
    resp = auth_session.get("/secrets/?path=prod/db")
    assert resp.status_code == 200
    assert b"password" in resp.data
    assert b"host" in resp.data


@responses.activate
def test_secrets_list_root_shows_folders(auth_session):
    get_cache().clear()
    responses.add(
        responses.GET, "http://barbican.test/v1/secrets",
        json={
            "secrets": [
                {"secret_ref": "http://barbican.test/v1/secrets/s1", "name": "prod/db/password", "status": "ACTIVE", "secret_type": "opaque"},
                {"secret_ref": "http://barbican.test/v1/secrets/s2", "name": "root-secret", "status": "ACTIVE", "secret_type": "opaque"},
            ],
            "total": 2,
        },
    )
    resp = auth_session.get("/secrets/")
    assert resp.status_code == 200
    assert b"root-secret" in resp.data


@responses.activate
def test_secrets_create_with_path_prefix(auth_session):
    get_cache().clear()
    responses.add(
        responses.POST, "http://barbican.test/v1/secrets",
        json={"secret_ref": "http://barbican.test/v1/secrets/new-id"},
        status=201,
    )
    resp = auth_session.post("/secrets/create", data={
        "path_prefix": "prod/db",
        "name": "new-password",
        "secret_type": "opaque",
        "payload_mode": "simple",
        "payload": "s3cret",
        "payload_content_type": "text/plain",
    }, follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_secrets_create_json_mode(auth_session):
    get_cache().clear()
    responses.add(
        responses.POST, "http://barbican.test/v1/secrets",
        json={"secret_ref": "http://barbican.test/v1/secrets/json-id"},
        status=201,
    )
    resp = auth_session.post("/secrets/create", data={
        "name": "json-secret",
        "secret_type": "opaque",
        "payload_mode": "json",
        "json_payload": '{"key": "value"}',
    }, follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_secrets_update_kv_mode(auth_session):
    get_cache().clear()
    responses.add(responses.PUT, "http://barbican.test/v1/secrets/s1", status=204)
    resp = auth_session.post("/secrets/s1/update", data={
        "payload_mode": "kv",
        "kv_key": ["host", "port"],
        "kv_value": ["localhost", "5432"],
    }, follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_secrets_update_json_mode(auth_session):
    get_cache().clear()
    responses.add(responses.PUT, "http://barbican.test/v1/secrets/s1", status=204)
    resp = auth_session.post("/secrets/s1/update", data={
        "payload_mode": "json",
        "json_payload": '{"a": 1}',
    }, follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_secrets_detail_no_payload(auth_session):
    """Secret without ACTIVE status should not attempt payload fetch."""
    get_cache().clear()
    secret = {**SAMPLE_SECRET, "status": "PENDING"}
    responses.add(responses.GET, "http://barbican.test/v1/secrets/s1", json=secret)
    resp = auth_session.get("/secrets/s1")
    assert resp.status_code == 200


@responses.activate
def test_secrets_create_error_handling(auth_session):
    get_cache().clear()
    responses.add(responses.POST, "http://barbican.test/v1/secrets", json={"title": "Conflict"}, status=409)
    resp = auth_session.post("/secrets/create", data={
        "name": "dup", "secret_type": "opaque", "payload_mode": "simple",
        "payload": "val", "payload_content_type": "text/plain",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "/secrets/create" in resp.headers["Location"]


@responses.activate
def test_secrets_list_with_name_filter(auth_session):
    """Search by name should skip folder logic and show all matching secrets."""
    get_cache().clear()
    responses.add(
        responses.GET, f"{BARBICAN}/v1/secrets",
        json={
            "secrets": [
                {"secret_ref": f"{BARBICAN}/v1/secrets/s1", "name": "prod/db/password", "status": "ACTIVE", "secret_type": "opaque"},
            ],
            "total": 1,
        },
    )
    resp = auth_session.get("/secrets/?name=password")
    assert resp.status_code == 200
    assert b"password" in resp.data


@responses.activate
def test_secrets_list_api_error(auth_session):
    """Barbican error during list should flash message, not crash."""
    get_cache().clear()
    responses.add(responses.GET, f"{BARBICAN}/v1/secrets", json={"title": "Internal Error"}, status=500)
    resp = auth_session.get("/secrets/")
    assert resp.status_code == 200  # still renders page


@responses.activate
def test_secrets_detail_payload_error(auth_session):
    """When payload fetch fails, should still show detail page with error."""
    get_cache().clear()
    responses.add(responses.GET, f"{BARBICAN}/v1/secrets/s1", json=SAMPLE_SECRET)
    responses.add(responses.GET, f"{BARBICAN}/v1/secrets/s1/payload", json={"title": "Forbidden"}, status=403)
    resp = auth_session.get("/secrets/s1")
    assert resp.status_code == 200


@responses.activate
def test_secrets_detail_json_payload(auth_session):
    """Secret with JSON payload should parse and display."""
    get_cache().clear()
    responses.add(responses.GET, f"{BARBICAN}/v1/secrets/s1", json=SAMPLE_SECRET)
    responses.add(responses.GET, f"{BARBICAN}/v1/secrets/s1/payload", body='{"db_host": "localhost"}')
    resp = auth_session.get("/secrets/s1")
    assert resp.status_code == 200
    assert b"db_host" in resp.data


@responses.activate
def test_secrets_detail_non_dict_json_payload(auth_session):
    """Non-dict JSON payload (e.g. list) should not be treated as KV."""
    get_cache().clear()
    responses.add(responses.GET, f"{BARBICAN}/v1/secrets/s1", json=SAMPLE_SECRET)
    responses.add(responses.GET, f"{BARBICAN}/v1/secrets/s1/payload", body='[1, 2, 3]')
    resp = auth_session.get("/secrets/s1")
    assert resp.status_code == 200


@responses.activate
def test_secrets_detail_error_redirect(auth_session):
    """Barbican error on get_secret should redirect to list."""
    get_cache().clear()
    responses.add(responses.GET, f"{BARBICAN}/v1/secrets/s1", json={"title": "Not Found"}, status=404)
    resp = auth_session.get("/secrets/s1", follow_redirects=False)
    assert resp.status_code == 302
    assert "/secrets" in resp.headers["Location"]


@responses.activate
def test_secrets_update_error(auth_session):
    """Barbican error on update should flash and redirect back."""
    get_cache().clear()
    responses.add(responses.PUT, f"{BARBICAN}/v1/secrets/s1", json={"title": "Conflict"}, status=409)
    resp = auth_session.post("/secrets/s1/update", data={
        "payload_mode": "simple", "payload": "new", "payload_content_type": "text/plain",
    }, follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_secrets_delete_error(auth_session):
    """Barbican error on delete should flash and redirect."""
    get_cache().clear()
    responses.add(responses.DELETE, f"{BARBICAN}/v1/secrets/s1", json={"title": "Forbidden"}, status=403)
    resp = auth_session.post("/secrets/s1/delete", follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_secrets_create_page_with_path(auth_session):
    """Create page should accept path query param and fetch folder tree."""
    get_cache().clear()
    responses.add(responses.GET, f"{BARBICAN}/v1/secrets", json={"secrets": [SAMPLE_SECRET], "total": 1})
    resp = auth_session.get("/secrets/create?path=prod/db")
    assert resp.status_code == 200


@responses.activate
def test_secrets_create_page_api_error(auth_session):
    """If secret list fails during create page load, should still render."""
    get_cache().clear()
    responses.add(responses.GET, f"{BARBICAN}/v1/secrets", json={"title": "Error"}, status=500)
    resp = auth_session.get("/secrets/create")
    assert resp.status_code == 200


# ── Container routes — more coverage ────────────────────────────────


@responses.activate
def test_containers_create_page(auth_session):
    get_cache().clear()
    responses.add(responses.GET, "http://barbican.test/v1/secrets", json={"secrets": [SAMPLE_SECRET], "total": 1})
    resp = auth_session.get("/containers/create")
    assert resp.status_code == 200


@responses.activate
def test_containers_create_post(auth_session):
    get_cache().clear()
    responses.add(
        responses.POST, "http://barbican.test/v1/containers",
        json={"container_ref": "http://barbican.test/v1/containers/new-c"}, status=201,
    )
    resp = auth_session.post("/containers/create", data={
        "name": "my-container", "type": "generic",
        "ref_name": ["secret1"], "ref_id": ["s1"],
    }, follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_containers_delete(auth_session):
    get_cache().clear()
    responses.add(responses.DELETE, "http://barbican.test/v1/containers/c1", status=204)
    resp = auth_session.post("/containers/c1/delete", follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_containers_detail_with_secret_refs(auth_session):
    get_cache().clear()
    container = {
        **SAMPLE_CONTAINER,
        "secret_refs": [
            {"name": "key", "secret_ref": "http://barbican.test/v1/secrets/s1"}
        ],
    }
    responses.add(responses.GET, "http://barbican.test/v1/containers/c1", json=container)
    responses.add(responses.GET, "http://barbican.test/v1/containers/c1/consumers", json={"consumers": [{"name": "app", "URL": "http://app.test"}], "total": 1})
    resp = auth_session.get("/containers/c1")
    assert resp.status_code == 200


@responses.activate
def test_containers_list_error(auth_session):
    get_cache().clear()
    responses.add(responses.GET, f"{BARBICAN}/v1/containers", json={"title": "Error"}, status=500)
    resp = auth_session.get("/containers/")
    assert resp.status_code == 200


@responses.activate
def test_containers_list_pagination(auth_session):
    get_cache().clear()
    responses.add(responses.GET, f"{BARBICAN}/v1/containers", json={"containers": [], "total": 100})
    resp = auth_session.get("/containers/?page=3")
    assert resp.status_code == 200


@responses.activate
def test_containers_detail_error(auth_session):
    get_cache().clear()
    responses.add(responses.GET, f"{BARBICAN}/v1/containers/c1", json={"title": "Not Found"}, status=404)
    resp = auth_session.get("/containers/c1", follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_containers_detail_consumer_error(auth_session):
    """Consumer list failure should not crash container detail page."""
    get_cache().clear()
    responses.add(responses.GET, f"{BARBICAN}/v1/containers/c1", json=SAMPLE_CONTAINER)
    responses.add(responses.GET, f"{BARBICAN}/v1/containers/c1/consumers", json={"title": "Error"}, status=500)
    resp = auth_session.get("/containers/c1")
    assert resp.status_code == 200


@responses.activate
def test_containers_create_error(auth_session):
    get_cache().clear()
    responses.add(responses.POST, f"{BARBICAN}/v1/containers", json={"title": "Bad"}, status=400)
    resp = auth_session.post("/containers/create", data={
        "name": "bad-ctr", "type": "generic", "ref_name": [], "ref_id": [],
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "/containers/create" in resp.headers["Location"]


@responses.activate
def test_containers_delete_error(auth_session):
    get_cache().clear()
    responses.add(responses.DELETE, f"{BARBICAN}/v1/containers/c1", json={"title": "Forbidden"}, status=403)
    resp = auth_session.post("/containers/c1/delete", follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_containers_create_page_secret_list_error(auth_session):
    """If fetching secrets for the create page fails, should still render."""
    get_cache().clear()
    responses.add(responses.GET, f"{BARBICAN}/v1/secrets", json={"title": "Error"}, status=500)
    resp = auth_session.get("/containers/create")
    assert resp.status_code == 200


# ── Consumer routes ─────────────────────────────────────────────────


@responses.activate
def test_consumer_create_missing_fields(auth_session):
    resp = auth_session.post("/consumers/c1/create", data={"name": "", "url": ""}, follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_consumer_delete(auth_session):
    get_cache().clear()
    responses.add(responses.DELETE, "http://barbican.test/v1/containers/c1/consumers", status=204)
    resp = auth_session.post("/consumers/c1/delete", data={"name": "app", "url": "http://app.test"}, follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_consumer_create_success(auth_session):
    get_cache().clear()
    responses.add(responses.POST, f"{BARBICAN}/v1/containers/c1/consumers", json={"name": "app", "URL": "http://app"}, status=200)
    resp = auth_session.post("/consumers/c1/create", data={"name": "app", "url": "http://app"}, follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_consumer_create_error(auth_session):
    get_cache().clear()
    responses.add(responses.POST, f"{BARBICAN}/v1/containers/c1/consumers", json={"title": "Error"}, status=400)
    resp = auth_session.post("/consumers/c1/create", data={"name": "app", "url": "http://app"}, follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_consumer_delete_error(auth_session):
    get_cache().clear()
    responses.add(responses.DELETE, f"{BARBICAN}/v1/containers/c1/consumers", json={"title": "Error"}, status=400)
    resp = auth_session.post("/consumers/c1/delete", data={"name": "app", "url": "http://app"}, follow_redirects=False)
    assert resp.status_code == 302


# ── Order routes — more coverage ────────────────────────────────────


@responses.activate
def test_orders_create_page(auth_session):
    resp = auth_session.get("/orders/create")
    assert resp.status_code == 200


@responses.activate
def test_orders_create_post(auth_session):
    get_cache().clear()
    responses.add(
        responses.POST, "http://barbican.test/v1/orders",
        json={"order_ref": "http://barbican.test/v1/orders/new-o"}, status=202,
    )
    resp = auth_session.post("/orders/create", data={
        "type": "key", "name": "mykey", "algorithm": "aes",
        "bit_length": "256", "mode": "cbc",
        "payload_content_type": "application/octet-stream",
    }, follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_orders_delete(auth_session):
    get_cache().clear()
    responses.add(responses.DELETE, "http://barbican.test/v1/orders/o1", status=204)
    resp = auth_session.post("/orders/o1/delete", follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_orders_detail_error(auth_session):
    get_cache().clear()
    responses.add(responses.GET, "http://barbican.test/v1/orders/bad", json={"title": "Not Found"}, status=404)
    resp = auth_session.get("/orders/bad", follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_orders_list_error(auth_session):
    get_cache().clear()
    responses.add(responses.GET, f"{BARBICAN}/v1/orders", json={"title": "Error"}, status=500)
    resp = auth_session.get("/orders/")
    assert resp.status_code == 200


@responses.activate
def test_orders_list_pagination(auth_session):
    get_cache().clear()
    responses.add(responses.GET, f"{BARBICAN}/v1/orders", json={"orders": [], "total": 0})
    resp = auth_session.get("/orders/?page=2")
    assert resp.status_code == 200


@responses.activate
def test_orders_create_error(auth_session):
    get_cache().clear()
    responses.add(responses.POST, f"{BARBICAN}/v1/orders", json={"title": "Bad"}, status=400)
    resp = auth_session.post("/orders/create", data={
        "type": "key", "name": "k", "algorithm": "aes", "bit_length": "256",
        "mode": "cbc", "payload_content_type": "application/octet-stream",
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "/orders/create" in resp.headers["Location"]


@responses.activate
def test_orders_delete_error(auth_session):
    get_cache().clear()
    responses.add(responses.DELETE, f"{BARBICAN}/v1/orders/o1", json={"title": "Forbidden"}, status=403)
    resp = auth_session.post("/orders/o1/delete", follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_orders_create_with_expiration(auth_session):
    get_cache().clear()
    responses.add(responses.POST, f"{BARBICAN}/v1/orders", json={"order_ref": f"{BARBICAN}/v1/orders/o1"}, status=202)
    resp = auth_session.post("/orders/create", data={
        "type": "key", "name": "k", "algorithm": "aes", "bit_length": "256",
        "mode": "cbc", "payload_content_type": "application/octet-stream",
        "expiration": "2030-01-01T00:00:00",
    }, follow_redirects=False)
    assert resp.status_code == 302


# ── Transfer routes — comprehensive coverage ────────────────────────


@responses.activate
def test_transfer_index(auth_session):
    resp = auth_session.get("/transfer/")
    assert resp.status_code == 200


@responses.activate
def test_transfer_export_secrets_only(auth_session):
    get_cache().clear()
    responses.add(
        responses.GET, "http://barbican.test/v1/secrets",
        json={"secrets": [SAMPLE_SECRET], "total": 1},
    )
    responses.add(
        responses.GET, "http://barbican.test/v1/secrets/sec-uuid-1/payload",
        body="my-value",
    )
    resp = auth_session.post("/transfer/export", data={
        "include": ["secrets", "payloads"],
    })
    assert resp.status_code == 200
    assert resp.content_type == "application/json"
    data = json.loads(resp.data)
    assert data["version"] == "1.0"
    assert len(data["secrets"]) == 1
    assert data["secrets"][0]["payload"] == "my-value"


@responses.activate
def test_transfer_export_containers(auth_session):
    get_cache().clear()
    responses.add(
        responses.GET, "http://barbican.test/v1/secrets",
        json={"secrets": [SAMPLE_SECRET], "total": 1},
    )
    responses.add(
        responses.GET, "http://barbican.test/v1/containers",
        json={"containers": [SAMPLE_CONTAINER], "total": 1},
    )
    responses.add(
        responses.GET, "http://barbican.test/v1/containers/ctr-uuid-1/consumers",
        json={"consumers": [], "total": 0},
    )
    resp = auth_session.post("/transfer/export", data={
        "include": ["containers"],
    })
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert len(data["containers"]) == 1


@responses.activate
def test_transfer_import_dry_run(auth_session):
    get_cache().clear()
    export_data = {
        "version": "1.0",
        "secrets": [
            {"name": "imported-secret", "secret_type": "opaque", "payload": "val", "payload_content_type": "text/plain"},
        ],
        "containers": [],
    }
    data = io.BytesIO(json.dumps(export_data).encode())
    resp = auth_session.post("/transfer/import", data={
        "dry_run": "on",
        "file": (data, "export.json"),
    }, content_type="multipart/form-data", follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_transfer_import_real(auth_session):
    get_cache().clear()
    responses.add(
        responses.POST, "http://barbican.test/v1/secrets",
        json={"secret_ref": "http://barbican.test/v1/secrets/imported-1"}, status=201,
    )
    export_data = {
        "version": "1.0",
        "secrets": [
            {"name": "imported-secret", "secret_type": "opaque", "payload": "val", "payload_content_type": "text/plain"},
        ],
        "containers": [],
    }
    data = io.BytesIO(json.dumps(export_data).encode())
    resp = auth_session.post("/transfer/import", data={
        "file": (data, "export.json"),
    }, content_type="multipart/form-data", follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_transfer_import_invalid_json(auth_session):
    data = io.BytesIO(b"not-json")
    resp = auth_session.post("/transfer/import", data={
        "file": (data, "bad.json"),
    }, content_type="multipart/form-data", follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_transfer_import_wrong_version(auth_session):
    export_data = {"version": "99.0", "secrets": [], "containers": []}
    data = io.BytesIO(json.dumps(export_data).encode())
    resp = auth_session.post("/transfer/import", data={
        "file": (data, "export.json"),
    }, content_type="multipart/form-data", follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_transfer_import_no_file(auth_session):
    resp = auth_session.post("/transfer/import", data={}, follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_transfer_import_skip_existing(auth_session):
    get_cache().clear()
    # Existing secrets list
    responses.add(
        responses.GET, "http://barbican.test/v1/secrets",
        json={"secrets": [SAMPLE_SECRET], "total": 1},
    )
    export_data = {
        "version": "1.0",
        "secrets": [
            {"name": "test-secret", "secret_type": "opaque", "payload": "val", "payload_content_type": "text/plain"},
        ],
        "containers": [],
    }
    data = io.BytesIO(json.dumps(export_data).encode())
    resp = auth_session.post("/transfer/import", data={
        "skip_existing": "on",
        "file": (data, "export.json"),
    }, content_type="multipart/form-data", follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_transfer_export_no_includes(auth_session):
    """Export with nothing included should return empty JSON."""
    get_cache().clear()
    resp = auth_session.post("/transfer/export", data={
        "include": [],
    })
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["secrets"] == []
    assert data["containers"] == []


@responses.activate
def test_transfer_export_secrets_without_payloads(auth_session):
    """Export secrets without payloads — payload should be None."""
    get_cache().clear()
    responses.add(
        responses.GET, f"{BARBICAN}/v1/secrets",
        json={"secrets": [SAMPLE_SECRET], "total": 1},
    )
    resp = auth_session.post("/transfer/export", data={
        "include": ["secrets"],
    })
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert len(data["secrets"]) == 1
    assert data["secrets"][0]["payload"] is None


@responses.activate
def test_transfer_export_payload_fetch_error(auth_session):
    """When payload fetch fails, entry should have payload_error."""
    get_cache().clear()
    responses.add(
        responses.GET, f"{BARBICAN}/v1/secrets",
        json={"secrets": [SAMPLE_SECRET], "total": 1},
    )
    responses.add(
        responses.GET, f"{BARBICAN}/v1/secrets/sec-uuid-1/payload",
        json={"title": "Forbidden"}, status=403,
    )
    resp = auth_session.post("/transfer/export", data={
        "include": ["secrets", "payloads"],
    })
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "payload_error" in data["secrets"][0]


@responses.activate
def test_transfer_export_secret_list_error(auth_session):
    """When secret list fails during export, should redirect with flash."""
    get_cache().clear()
    responses.add(
        responses.GET, f"{BARBICAN}/v1/secrets",
        json={"title": "Internal Error"}, status=500,
    )
    resp = auth_session.post("/transfer/export", data={
        "include": ["secrets"],
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "/transfer" in resp.headers["Location"]


@responses.activate
def test_transfer_export_container_list_error(auth_session):
    """When container list fails during export, should redirect with flash."""
    get_cache().clear()
    # Secrets list succeeds (needed because include_containers triggers secret fetch too)
    responses.add(
        responses.GET, f"{BARBICAN}/v1/secrets",
        json={"secrets": [], "total": 0},
    )
    responses.add(
        responses.GET, f"{BARBICAN}/v1/containers",
        json={"title": "Error"}, status=500,
    )
    resp = auth_session.post("/transfer/export", data={
        "include": ["containers"],
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert "/transfer" in resp.headers["Location"]


@responses.activate
def test_transfer_export_containers_with_consumers(auth_session):
    """Export containers that have consumers."""
    get_cache().clear()
    container_with_refs = {
        "container_ref": f"{BARBICAN}/v1/containers/ctr-1",
        "name": "my-ctr",
        "type": "generic",
        "secret_refs": [{"name": "key", "secret_ref": f"{BARBICAN}/v1/secrets/sec-uuid-1"}],
        "created": "2026-01-01",
    }
    responses.add(responses.GET, f"{BARBICAN}/v1/secrets", json={"secrets": [SAMPLE_SECRET], "total": 1})
    responses.add(responses.GET, f"{BARBICAN}/v1/containers", json={"containers": [container_with_refs], "total": 1})
    responses.add(responses.GET, f"{BARBICAN}/v1/containers/ctr-1/consumers", json={
        "consumers": [{"name": "myapp", "URL": "http://myapp.test"}], "total": 1,
    })
    resp = auth_session.post("/transfer/export", data={"include": ["containers"]})
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert len(data["containers"]) == 1
    assert data["containers"][0]["consumers"][0]["name"] == "myapp"
    assert data["containers"][0]["secret_refs"][0]["secret_name"] == "test-secret"


@responses.activate
def test_transfer_export_consumer_list_error_on_container(auth_session):
    """Consumer list error during container export should not crash."""
    get_cache().clear()
    responses.add(responses.GET, f"{BARBICAN}/v1/secrets", json={"secrets": [], "total": 0})
    responses.add(responses.GET, f"{BARBICAN}/v1/containers", json={"containers": [SAMPLE_CONTAINER], "total": 1})
    responses.add(responses.GET, f"{BARBICAN}/v1/containers/ctr-uuid-1/consumers", json={"title": "Error"}, status=500)
    resp = auth_session.post("/transfer/export", data={"include": ["containers"]})
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["containers"][0]["consumers"] == []


@responses.activate
def test_transfer_export_secrets_and_containers(auth_session):
    """Export both secrets and containers together."""
    get_cache().clear()
    responses.add(responses.GET, f"{BARBICAN}/v1/secrets", json={"secrets": [SAMPLE_SECRET], "total": 1})
    responses.add(responses.GET, f"{BARBICAN}/v1/containers", json={"containers": [SAMPLE_CONTAINER], "total": 1})
    responses.add(responses.GET, f"{BARBICAN}/v1/containers/ctr-uuid-1/consumers", json={"consumers": [], "total": 0})
    resp = auth_session.post("/transfer/export", data={"include": ["secrets", "containers"]})
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert len(data["secrets"]) == 1
    assert len(data["containers"]) == 1
    # Check filename header
    assert "Content-Disposition" in resp.headers
    assert "barbican_export_" in resp.headers["Content-Disposition"]


@responses.activate
def test_transfer_import_with_containers_and_consumers(auth_session):
    """Import containers with secret refs and consumers."""
    get_cache().clear()
    # Import creates secrets, then containers, then consumers
    responses.add(responses.POST, f"{BARBICAN}/v1/secrets",
        json={"secret_ref": f"{BARBICAN}/v1/secrets/new-s1"}, status=201)
    responses.add(responses.POST, f"{BARBICAN}/v1/containers",
        json={"container_ref": f"{BARBICAN}/v1/containers/new-c1"}, status=201)
    responses.add(responses.POST, f"{BARBICAN}/v1/containers/new-c1/consumers",
        json={"name": "app", "URL": "http://app.test"}, status=200)

    export_data = {
        "version": "1.0",
        "secrets": [{"name": "my-secret", "secret_type": "opaque", "payload": "val", "payload_content_type": "text/plain"}],
        "containers": [{
            "name": "my-ctr",
            "type": "generic",
            "secret_refs": [{"name": "key", "secret_name": "my-secret"}],
            "consumers": [{"name": "app", "url": "http://app.test"}],
        }],
    }
    data = io.BytesIO(json.dumps(export_data).encode())
    resp = auth_session.post("/transfer/import", data={
        "file": (data, "export.json"),
    }, content_type="multipart/form-data", follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_transfer_import_container_missing_secret_ref(auth_session):
    """Import container whose secret_ref can't be resolved should add error."""
    get_cache().clear()
    responses.add(responses.POST, f"{BARBICAN}/v1/containers",
        json={"container_ref": f"{BARBICAN}/v1/containers/new-c1"}, status=201)

    export_data = {
        "version": "1.0",
        "secrets": [],
        "containers": [{
            "name": "my-ctr",
            "type": "generic",
            "secret_refs": [{"name": "key", "secret_name": "nonexistent-secret"}],
            "consumers": [],
        }],
    }
    data = io.BytesIO(json.dumps(export_data).encode())
    resp = auth_session.post("/transfer/import", data={
        "file": (data, "export.json"),
    }, content_type="multipart/form-data", follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_transfer_import_container_create_error(auth_session):
    """Container creation failure during import should be recorded."""
    get_cache().clear()
    responses.add(responses.POST, f"{BARBICAN}/v1/containers",
        json={"title": "Bad Request"}, status=400)

    export_data = {
        "version": "1.0",
        "secrets": [],
        "containers": [{"name": "bad-ctr", "type": "generic", "secret_refs": [], "consumers": []}],
    }
    data = io.BytesIO(json.dumps(export_data).encode())
    resp = auth_session.post("/transfer/import", data={
        "file": (data, "export.json"),
    }, content_type="multipart/form-data", follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_transfer_import_consumer_create_error(auth_session):
    """Consumer registration failure during import should be recorded."""
    get_cache().clear()
    responses.add(responses.POST, f"{BARBICAN}/v1/containers",
        json={"container_ref": f"{BARBICAN}/v1/containers/new-c1"}, status=201)
    responses.add(responses.POST, f"{BARBICAN}/v1/containers/new-c1/consumers",
        json={"title": "Error"}, status=400)

    export_data = {
        "version": "1.0",
        "secrets": [],
        "containers": [{
            "name": "my-ctr", "type": "generic", "secret_refs": [],
            "consumers": [{"name": "bad-app", "url": "http://bad"}],
        }],
    }
    data = io.BytesIO(json.dumps(export_data).encode())
    resp = auth_session.post("/transfer/import", data={
        "file": (data, "export.json"),
    }, content_type="multipart/form-data", follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_transfer_import_secret_store_error(auth_session):
    """Secret store failure during import should be recorded."""
    get_cache().clear()
    responses.add(responses.POST, f"{BARBICAN}/v1/secrets",
        json={"title": "Conflict"}, status=409)

    export_data = {
        "version": "1.0",
        "secrets": [{"name": "fail-secret", "secret_type": "opaque", "payload": "v", "payload_content_type": "text/plain"}],
        "containers": [],
    }
    data = io.BytesIO(json.dumps(export_data).encode())
    resp = auth_session.post("/transfer/import", data={
        "file": (data, "export.json"),
    }, content_type="multipart/form-data", follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_transfer_import_dry_run_with_containers(auth_session):
    """Dry run should count containers without creating."""
    get_cache().clear()
    export_data = {
        "version": "1.0",
        "secrets": [{"name": "s1", "secret_type": "opaque", "payload": "v", "payload_content_type": "text/plain"}],
        "containers": [{"name": "c1", "type": "generic", "secret_refs": [], "consumers": []}],
    }
    data = io.BytesIO(json.dumps(export_data).encode())
    resp = auth_session.post("/transfer/import", data={
        "dry_run": "on",
        "file": (data, "export.json"),
    }, content_type="multipart/form-data", follow_redirects=False)
    assert resp.status_code == 302
    # No API calls should have been made (except maybe existing secret check)
    assert len(responses.calls) == 0


@responses.activate
def test_transfer_import_skip_existing_with_containers(auth_session):
    """Skip existing + real import should map existing secrets for container refs."""
    get_cache().clear()
    # First call: check existing secrets (skip_existing)
    # Second call: re-list to map names to IDs
    responses.add(responses.GET, f"{BARBICAN}/v1/secrets",
        json={"secrets": [SAMPLE_SECRET], "total": 1})
    responses.add(responses.GET, f"{BARBICAN}/v1/secrets",
        json={"secrets": [SAMPLE_SECRET], "total": 1})
    responses.add(responses.POST, f"{BARBICAN}/v1/containers",
        json={"container_ref": f"{BARBICAN}/v1/containers/new-c1"}, status=201)

    export_data = {
        "version": "1.0",
        "secrets": [{"name": "test-secret", "secret_type": "opaque", "payload": "v", "payload_content_type": "text/plain"}],
        "containers": [{
            "name": "ctr", "type": "generic",
            "secret_refs": [{"name": "key", "secret_name": "test-secret"}],
            "consumers": [],
        }],
    }
    data = io.BytesIO(json.dumps(export_data).encode())
    resp = auth_session.post("/transfer/import", data={
        "skip_existing": "on",
        "file": (data, "export.json"),
    }, content_type="multipart/form-data", follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_transfer_import_many_errors_truncated(auth_session):
    """When >10 errors, only first 10 should be flashed plus a count."""
    get_cache().clear()
    # Make 12 secrets all fail
    for _ in range(12):
        responses.add(responses.POST, f"{BARBICAN}/v1/secrets",
            json={"title": "Error"}, status=400)

    secrets = [{"name": f"s{i}", "secret_type": "opaque", "payload": "v", "payload_content_type": "text/plain"} for i in range(12)]
    export_data = {"version": "1.0", "secrets": secrets, "containers": []}
    data = io.BytesIO(json.dumps(export_data).encode())
    resp = auth_session.post("/transfer/import", data={
        "file": (data, "export.json"),
    }, content_type="multipart/form-data", follow_redirects=False)
    assert resp.status_code == 302


@responses.activate
def test_transfer_export_inactive_secret_no_payload(auth_session):
    """Inactive secrets should not have payload fetched even if payloads requested."""
    get_cache().clear()
    inactive = {**SAMPLE_SECRET, "status": "PENDING"}
    responses.add(responses.GET, f"{BARBICAN}/v1/secrets", json={"secrets": [inactive], "total": 1})
    resp = auth_session.post("/transfer/export", data={"include": ["secrets", "payloads"]})
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["secrets"][0]["payload"] is None
    # No payload fetch call should have been made
    assert len(responses.calls) == 1  # only the list call


@responses.activate
def test_transfer_export_containers_only_builds_id_map(auth_session):
    """Export containers-only should still fetch secrets to build id→name map."""
    get_cache().clear()
    secret_with_id = {
        "secret_ref": f"{BARBICAN}/v1/secrets/my-sec-id",
        "name": "mapped-secret",
        "status": "ACTIVE",
        "secret_type": "opaque",
    }
    container_with_ref = {
        "container_ref": f"{BARBICAN}/v1/containers/c1",
        "name": "ctr",
        "type": "generic",
        "secret_refs": [{"name": "ref", "secret_ref": f"{BARBICAN}/v1/secrets/my-sec-id"}],
    }
    responses.add(responses.GET, f"{BARBICAN}/v1/secrets", json={"secrets": [secret_with_id], "total": 1})
    responses.add(responses.GET, f"{BARBICAN}/v1/containers", json={"containers": [container_with_ref], "total": 1})
    responses.add(responses.GET, f"{BARBICAN}/v1/containers/c1/consumers", json={"consumers": [], "total": 0})

    resp = auth_session.post("/transfer/export", data={"include": ["containers"]})
    assert resp.status_code == 200
    data = json.loads(resp.data)
    # Secret names should be in the export, not IDs
    assert data["containers"][0]["secret_refs"][0]["secret_name"] == "mapped-secret"
    # No secrets should be in the secrets array (only containers requested)
    assert data["secrets"] == []


@responses.activate
def test_transfer_import_secret_with_none_payload(auth_session):
    """Import a secret that has no payload (None) — should still work."""
    get_cache().clear()
    responses.add(responses.POST, f"{BARBICAN}/v1/secrets",
        json={"secret_ref": f"{BARBICAN}/v1/secrets/np1"}, status=201)

    export_data = {
        "version": "1.0",
        "secrets": [{"name": "empty-secret", "secret_type": "opaque", "payload": None, "payload_content_type": None}],
        "containers": [],
    }
    data = io.BytesIO(json.dumps(export_data).encode())
    resp = auth_session.post("/transfer/import", data={
        "file": (data, "export.json"),
    }, content_type="multipart/form-data", follow_redirects=False)
    assert resp.status_code == 302


# ── Helpers — IP binding ────────────────────────────────────────────


def test_session_ip_binding_rejects_different_ip(app):
    """With SESSION_BIND_IP=true, session from different IP should be rejected."""
    import os
    old = os.environ.get("SESSION_BIND_IP", "")
    os.environ["SESSION_BIND_IP"] = "true"
    from app.config import Config
    Config._load()

    with app.test_request_context(environ_base={"REMOTE_ADDR": "10.0.0.2"}):
        from flask import session
        from app.routes.helpers import get_auth
        session["auth"] = {
            "token": "tok",
            "expires_at": "2099-12-31T23:59:59+00:00",
            "project_id": "p1",
            "project_name": "proj",
            "user_id": "u1",
            "user_name": "user",
            "barbican_endpoint": "http://barbican.test",
            "client_ip": "10.0.0.1",  # different IP
        }
        assert get_auth() is None

    os.environ["SESSION_BIND_IP"] = old
    Config._load()


# ── Docs route ──────────────────────────────────────────────────────


def test_docs_page(auth_session):
    resp = auth_session.get("/docs")
    assert resp.status_code == 200


# ── Security headers ────────────────────────────────────────────────


def test_security_headers(client):
    resp = client.get("/healthz")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert "Content-Security-Policy" in resp.headers

