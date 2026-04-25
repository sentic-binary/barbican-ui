"""Unit tests for app.cache module."""

import pytest
from app.cache import get_cache, cache_get, cache_set, cache_delete, cache_invalidate_prefix


@pytest.fixture(autouse=True)
def clear_cache():
    get_cache().clear()
    yield
    get_cache().clear()


class TestCacheGetSet:
    def test_get_returns_none_for_missing_key(self):
        assert cache_get("nonexistent") is None

    def test_set_and_get(self):
        cache_set("key1", {"data": "value"})
        assert cache_get("key1") == {"data": "value"}

    def test_set_with_custom_ttl(self):
        cache_set("key2", "val", ttl=9999)
        assert cache_get("key2") == "val"

    def test_set_overwrites_existing(self):
        cache_set("key3", "old")
        cache_set("key3", "new")
        assert cache_get("key3") == "new"

    def test_stores_list(self):
        cache_set("list_key", [1, 2, 3])
        assert cache_get("list_key") == [1, 2, 3]

    def test_stores_nested_dict(self):
        data = {"secrets": [{"name": "a"}, {"name": "b"}], "total": 2}
        cache_set("nested", data)
        assert cache_get("nested") == data


class TestCacheDelete:
    def test_delete_existing(self):
        cache_set("to_delete", "val")
        cache_delete("to_delete")
        assert cache_get("to_delete") is None

    def test_delete_nonexistent_no_error(self):
        cache_delete("does_not_exist")  # should not raise


class TestCacheInvalidatePrefix:
    def test_invalidate_matching_keys(self):
        cache_set("proj:secrets:list:1", "a")
        cache_set("proj:secrets:list:2", "b")
        cache_set("proj:containers:list:1", "c")
        cache_invalidate_prefix("proj:secrets")
        assert cache_get("proj:secrets:list:1") is None
        assert cache_get("proj:secrets:list:2") is None
        assert cache_get("proj:containers:list:1") == "c"

    def test_invalidate_no_match(self):
        cache_set("other:key", "val")
        cache_invalidate_prefix("proj:")
        assert cache_get("other:key") == "val"

    def test_invalidate_empty_prefix(self):
        cache_set("a", 1)
        cache_set("b", 2)
        cache_invalidate_prefix("")
        # Empty prefix matches everything
        assert cache_get("a") is None
        assert cache_get("b") is None


class TestGetCache:
    def test_returns_same_instance(self):
        c1 = get_cache()
        c2 = get_cache()
        assert c1 is c2

