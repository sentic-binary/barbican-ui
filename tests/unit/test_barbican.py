"""Unit tests for app.barbican module."""

import pytest
import responses

from app.barbican import (
    BarbicanError,
    secret_store, secret_list, secret_get, secret_get_payload,
    secret_delete, secret_update,
    container_create, container_list, container_get, container_delete,
    consumer_create, consumer_list, consumer_delete,
    order_create, order_list, order_get, order_delete,
)
from app.cache import get_cache

EP = "http://barbican.test"
TOKEN = "tok-123"
PID = "proj123"


@pytest.fixture(autouse=True)
def clear_cache():
    get_cache().clear()
    yield
    get_cache().clear()


# ── Secrets ────────────────────────────────────────────────────────

@responses.activate
def test_secret_store():
    responses.add(responses.POST, f"{EP}/v1/secrets", json={"secret_ref": f"{EP}/v1/secrets/s1"}, status=201)
    result = secret_store(EP, TOKEN, PID, name="s", payload="val")
    assert result["secret_ref"].endswith("s1")


@responses.activate
def test_secret_list():
    responses.add(responses.GET, f"{EP}/v1/secrets", json={"secrets": [{"name": "a"}], "total": 1})
    result = secret_list(EP, TOKEN, PID)
    assert result["total"] == 1
    # Second call should hit cache
    result2 = secret_list(EP, TOKEN, PID)
    assert result2["total"] == 1
    assert len(responses.calls) == 1  # only 1 HTTP call


@responses.activate
def test_secret_get():
    responses.add(responses.GET, f"{EP}/v1/secrets/s1", json={"name": "s", "status": "ACTIVE"})
    result = secret_get(EP, TOKEN, PID, "s1")
    assert result["name"] == "s"


@responses.activate
def test_secret_get_payload():
    responses.add(responses.GET, f"{EP}/v1/secrets/s1/payload", body="my-secret-value")
    result = secret_get_payload(EP, TOKEN, PID, "s1")
    assert result == "my-secret-value"


@responses.activate
def test_secret_delete():
    responses.add(responses.DELETE, f"{EP}/v1/secrets/s1", status=204)
    secret_delete(EP, TOKEN, PID, "s1")  # no exception


@responses.activate
def test_secret_update():
    responses.add(responses.PUT, f"{EP}/v1/secrets/s1", status=204)
    secret_update(EP, TOKEN, PID, "s1", payload="new-val")


@responses.activate
def test_secret_store_error():
    responses.add(responses.POST, f"{EP}/v1/secrets", json={"title": "Bad"}, status=400)
    with pytest.raises(BarbicanError):
        secret_store(EP, TOKEN, PID, name="x", payload="y")


# ── Containers ─────────────────────────────────────────────────────

@responses.activate
def test_container_create():
    responses.add(responses.POST, f"{EP}/v1/containers", json={"container_ref": f"{EP}/v1/containers/c1"}, status=201)
    result = container_create(EP, TOKEN, PID, name="c")
    assert "c1" in result["container_ref"]


@responses.activate
def test_container_list():
    responses.add(responses.GET, f"{EP}/v1/containers", json={"containers": [], "total": 0})
    result = container_list(EP, TOKEN, PID)
    assert result["total"] == 0


@responses.activate
def test_container_get():
    responses.add(responses.GET, f"{EP}/v1/containers/c1", json={"name": "c", "type": "generic"})
    result = container_get(EP, TOKEN, PID, "c1")
    assert result["type"] == "generic"


@responses.activate
def test_container_delete():
    responses.add(responses.DELETE, f"{EP}/v1/containers/c1", status=204)
    container_delete(EP, TOKEN, PID, "c1")


# ── Consumers ──────────────────────────────────────────────────────

@responses.activate
def test_consumer_create():
    responses.add(responses.POST, f"{EP}/v1/containers/c1/consumers", json={"name": "cons", "URL": "http://x"}, status=200)
    result = consumer_create(EP, TOKEN, PID, "c1", name="cons", url="http://x")
    assert result["name"] == "cons"


@responses.activate
def test_consumer_list():
    responses.add(responses.GET, f"{EP}/v1/containers/c1/consumers", json={"consumers": [], "total": 0})
    result = consumer_list(EP, TOKEN, PID, "c1")
    assert result["consumers"] == []


@responses.activate
def test_consumer_delete():
    responses.add(responses.DELETE, f"{EP}/v1/containers/c1/consumers", status=204)
    consumer_delete(EP, TOKEN, PID, "c1", name="cons", url="http://x")


# ── Orders ─────────────────────────────────────────────────────────

@responses.activate
def test_order_create():
    responses.add(responses.POST, f"{EP}/v1/orders", json={"order_ref": f"{EP}/v1/orders/o1"}, status=202)
    result = order_create(EP, TOKEN, PID, order_type="key", meta={"name": "k", "algorithm": "aes", "bit_length": 256})
    assert "o1" in result["order_ref"]


@responses.activate
def test_order_list():
    responses.add(responses.GET, f"{EP}/v1/orders", json={"orders": [], "total": 0})
    result = order_list(EP, TOKEN, PID)
    assert result["total"] == 0


@responses.activate
def test_order_get():
    responses.add(responses.GET, f"{EP}/v1/orders/o1", json={"type": "key", "status": "ACTIVE"})
    result = order_get(EP, TOKEN, PID, "o1")
    assert result["type"] == "key"


@responses.activate
def test_order_delete():
    responses.add(responses.DELETE, f"{EP}/v1/orders/o1", status=204)
    order_delete(EP, TOKEN, PID, "o1")

