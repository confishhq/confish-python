from __future__ import annotations

import hashlib
import hmac

import pytest

from confish.webhook import (
    WebhookPayload,
    WebhookSignatureError,
    WebhookTimestampError,
    verify,
)


def _sign(secret: str, ts: int, body: bytes) -> str:
    return hmac.new(secret.encode(), f"{ts}:".encode() + body, hashlib.sha256).hexdigest()


def test_returns_parsed_payload_for_valid_signature():
    body = (
        b'{"event":"environment.updated","timestamp":"2026-07-09T12:00:00+00:00",'
        b'"application":{"name":"My App"},'
        b'"environment":{"name":"production","env_id":"env_1","url":"https://confi.sh/c/env_1"},'
        b'"changes":["max_upload_mb"],"values":{"max_upload_mb":50}}'
    )
    ts = 1_700_000_000
    sig = _sign("whsec_test", ts, body)
    payload = verify(
        body=body,
        signature=f"ts={ts};sig={sig}",
        secret="whsec_test",
        now=ts,
    )
    assert isinstance(payload, WebhookPayload)
    assert payload.event == "environment.updated"
    assert payload.timestamp == "2026-07-09T12:00:00+00:00"
    assert payload.application == {"name": "My App"}
    assert payload.environment["env_id"] == "env_1"
    assert payload.changes == ["max_upload_mb"]
    assert payload.values == {"max_upload_mb": 50}


def test_raises_signature_error_on_wrong_secret():
    body = b'{"event":"environment.updated"}'
    ts = 1_700_000_000
    sig = _sign("other", ts, body)
    with pytest.raises(WebhookSignatureError):
        verify(
            body=body,
            signature=f"ts={ts};sig={sig}",
            secret="whsec_test",
            now=ts,
        )


def test_raises_signature_error_on_tampered_body():
    secret = "whsec_test"
    ts = 1_700_000_000
    sig = _sign(secret, ts, b'{"a":1}')
    with pytest.raises(WebhookSignatureError):
        verify(
            body=b'{"a":2}',
            signature=f"ts={ts};sig={sig}",
            secret=secret,
            now=ts,
        )


def test_raises_timestamp_error_on_stale_timestamp():
    secret = "whsec_test"
    ts = 1_700_000_000
    sig = _sign(secret, ts, b'{}')
    with pytest.raises(WebhookTimestampError):
        verify(
            body=b'{}',
            signature=f"ts={ts};sig={sig}",
            secret=secret,
            now=ts + 600,
            tolerance_seconds=300,
        )


def test_accepts_when_tolerance_disabled():
    secret = "whsec_test"
    ts = 1_700_000_000
    sig = _sign(secret, ts, b'{"event":"environment.updated"}')
    payload = verify(
        body=b'{"event":"environment.updated"}',
        signature=f"ts={ts};sig={sig}",
        secret=secret,
        now=ts + 99_999,
        tolerance_seconds=0,
    )
    assert payload.event == "environment.updated"


def test_raises_signature_error_on_malformed_headers():
    body = b'{}'
    secret = "whsec_test"
    for header in ["", "garbage", "ts=abc;sig=def", "ts=1;sig="]:
        with pytest.raises(WebhookSignatureError):
            verify(body=body, signature=header, secret=secret)
    with pytest.raises(WebhookSignatureError):
        verify(body=body, signature=None, secret=secret)


def test_accepts_string_body():
    body = '{"event":"environment.updated"}'
    ts = 1_700_000_000
    sig = _sign("whsec_test", ts, body.encode())
    payload = verify(
        body=body,
        signature=f"ts={ts};sig={sig}",
        secret="whsec_test",
        now=ts,
    )
    assert payload.event == "environment.updated"
