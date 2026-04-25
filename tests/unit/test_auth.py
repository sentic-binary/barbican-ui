"""Unit tests for app.auth module."""

import pytest
import requests
import responses

from app.auth import authenticate, AuthError


KEYSTONE_URL = "http://keystone.test/v3"


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

