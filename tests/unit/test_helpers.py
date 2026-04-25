"""Unit tests for app.routes.helpers module."""

import pytest
from app.routes.helpers import _extract_id, validate_resource_id, safe_error_message, safe_int


class TestExtractId:
    def test_extracts_uuid_from_href(self):
        assert _extract_id("http://barbican.test/v1/secrets/abc-123") == "abc-123"

    def test_extracts_from_trailing_slash(self):
        assert _extract_id("http://barbican.test/v1/secrets/abc-123/") == "abc-123"

    def test_empty_string(self):
        assert _extract_id("") == ""

    def test_no_slash(self):
        assert _extract_id("simple-id") == "simple-id"


class TestValidateResourceId:
    def test_valid_uuid(self, app):
        with app.test_request_context():
            assert validate_resource_id("abcdef12-3456-7890-abcd-ef1234567890") == "abcdef12-3456-7890-abcd-ef1234567890"

    def test_valid_simple_id(self, app):
        with app.test_request_context():
            assert validate_resource_id("my-secret-id") == "my-secret-id"

    def test_empty_id_aborts(self, app):
        with app.test_request_context():
            with pytest.raises(Exception):  # werkzeug HTTPException
                validate_resource_id("")

    def test_path_traversal_aborts(self, app):
        with app.test_request_context():
            with pytest.raises(Exception):
                validate_resource_id("../../etc/passwd")

    def test_slash_in_id_aborts(self, app):
        with app.test_request_context():
            with pytest.raises(Exception):
                validate_resource_id("foo/bar")


class TestSafeErrorMessage:
    def test_short_message(self):
        assert safe_error_message(Exception("short")) == "short"

    def test_truncates_long_message(self):
        msg = "x" * 500
        result = safe_error_message(Exception(msg))
        assert len(result) <= 301  # 300 + "…"
        assert result.endswith("…")


class TestSafeInt:
    def test_valid_int(self):
        assert safe_int("5") == 5

    def test_invalid_returns_default(self):
        assert safe_int("abc") == 1

    def test_custom_default(self):
        assert safe_int("abc", default=10) == 10

    def test_below_minimum(self):
        assert safe_int("0", minimum=1) == 1

    def test_negative_value_clamped(self):
        assert safe_int("-5", minimum=1) == 1

    def test_empty_string(self):
        assert safe_int("") == 1

    def test_none_value(self):
        assert safe_int(None) == 1


class TestGetAuth:
    def test_no_session_returns_none(self, app):
        with app.test_request_context():
            from flask import session
            from app.routes.helpers import get_auth
            session.clear()
            assert get_auth() is None

    def test_expired_token_clears_session(self, app):
        with app.test_request_context():
            from flask import session
            from app.routes.helpers import get_auth
            session["auth"] = {
                "token": "tok",
                "expires_at": "2020-01-01T00:00:00+00:00",
                "project_id": "p1",
                "project_name": "proj",
                "user_id": "u1",
                "user_name": "user",
                "barbican_endpoint": "http://barbican.test",
                "client_ip": "",
            }
            assert get_auth() is None

    def test_valid_token_returns_auth(self, app):
        with app.test_request_context():
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
                "client_ip": "",
            }
            auth = get_auth()
            assert auth is not None
            assert auth.token == "tok"
            assert auth.project_id == "p1"

    def test_corrupt_session_returns_none(self, app):
        with app.test_request_context():
            from flask import session
            from app.routes.helpers import get_auth
            session["auth"] = {"garbage": True}
            assert get_auth() is None


class TestSaveAuth:
    def test_saves_to_session(self, app):
        with app.test_request_context():
            from flask import session
            from app.routes.helpers import save_auth
            from app.auth import AuthToken
            from datetime import datetime, timezone
            token = AuthToken(
                token="t", expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
                project_id="p", project_name="pn", user_id="u", user_name="un",
                barbican_endpoint="http://b.test", catalog=[],
            )
            save_auth(token)
            assert session["auth"]["token"] == "t"
            assert session["auth"]["project_id"] == "p"
            assert session.permanent is True

