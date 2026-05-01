from __future__ import annotations

import pytest

from confish import (
    AuthError,
    Confish,
    ConflictError,
    RateLimitError,
    ValidationError,
)


def test_fetch_returns_typed_dict(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test",
        method="GET",
        json={"site_name": "My App", "max_upload_mb": 25, "maintenance_mode": False},
    )
    client = Confish(env_id="env_test", api_key="confish_sk_test", base_url="https://api.test")
    config = client.fetch()
    assert config["site_name"] == "My App"
    request = httpx_mock.get_request()
    assert request.headers["authorization"] == "Bearer confish_sk_test"


def test_update_wraps_values_in_patch(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test",
        method="PATCH",
        json={"site_name": "X", "max_upload_mb": 50, "maintenance_mode": True},
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")
    client.update({"maintenance_mode": True, "max_upload_mb": 50})

    import json
    body = json.loads(httpx_mock.get_request().content)
    assert body == {"values": {"maintenance_mode": True, "max_upload_mb": 50}}


def test_replace_uses_put(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test",
        method="PUT",
        json={},
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")
    client.replace({"site_name": "X"})
    assert httpx_mock.get_request().method == "PUT"


def test_auth_error_on_401(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test",
        method="GET",
        status_code=401,
        json={"error": "Missing API key"},
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")
    with pytest.raises(AuthError) as exc:
        client.fetch()
    assert exc.value.message == "Missing API key"


def test_validation_error_exposes_field_errors(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test",
        method="PATCH",
        status_code=422,
        json={
            "message": "invalid",
            "errors": {"values.max_upload_mb": ["Must be at most 100."]},
        },
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")
    with pytest.raises(ValidationError) as exc:
        client.update({"x": 1})
    assert exc.value.errors == {"values.max_upload_mb": ["Must be at most 100."]}


def test_rate_limit_retries_then_succeeds(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test",
        method="GET",
        status_code=429,
        json={"error": "limited"},
        headers={"retry-after": "0"},
    )
    httpx_mock.add_response(
        url="https://api.test/c/env_test",
        method="GET",
        json={"ok": True},
    )
    client = Confish(
        env_id="env_test", api_key="k", base_url="https://api.test",
        max_retries=1, max_retry_delay=0.01,
    )
    assert client.fetch() == {"ok": True}


def test_rate_limit_exhausts_retries(httpx_mock):
    for _ in range(3):  # initial + 2 retries
        httpx_mock.add_response(
            url="https://api.test/c/env_test",
            method="GET",
            status_code=429,
            json={"error": "limited"},
            headers={"retry-after": "0", "x-ratelimit-limit": "60"},
        )
    client = Confish(
        env_id="env_test", api_key="k", base_url="https://api.test",
        max_retries=2, max_retry_delay=0.01,
    )
    with pytest.raises(RateLimitError) as exc:
        client.fetch()
    assert exc.value.limit == 60


def test_conflict_on_ack(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test/actions/a1/ack",
        method="POST",
        status_code=409,
        json={"error": "already acknowledged"},
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")
    with pytest.raises(ConflictError):
        client.actions.ack("a1")


def test_logger_sends_level_and_context(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test/log",
        method="POST",
        status_code=201,
        json={"id": "log_1"},
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")
    log_id = client.logger.info("hello", {"user_id": 1})
    assert log_id == "log_1"

    import json
    body = json.loads(httpx_mock.get_request().content)
    assert body == {"level": "info", "message": "hello", "context": {"user_id": 1}}


def test_constructor_validates_required_fields():
    with pytest.raises(ValueError, match="env_id"):
        Confish(env_id="", api_key="k")
    with pytest.raises(ValueError, match="api_key"):
        Confish(env_id="e", api_key="")
