from __future__ import annotations

import hashlib
import hmac

from confish.webhook import verify


def _sign(secret: str, ts: int, body: bytes) -> str:
    return hmac.new(secret.encode(), f"{ts}:".encode() + body, hashlib.sha256).hexdigest()


def test_accepts_valid_signature():
    body = b'{"event":"environment.updated"}'
    ts = 1_700_000_000
    sig = _sign("whsec_test", ts, body)
    assert verify(
        body=body,
        signature=f"ts={ts};sig={sig}",
        secret="whsec_test",
        now=ts,
    )


def test_rejects_wrong_secret():
    body = b'{}'
    ts = 1_700_000_000
    sig = _sign("other", ts, body)
    assert not verify(
        body=body,
        signature=f"ts={ts};sig={sig}",
        secret="whsec_test",
        now=ts,
    )


def test_rejects_tampered_body():
    secret = "whsec_test"
    ts = 1_700_000_000
    sig = _sign(secret, ts, b'{"a":1}')
    assert not verify(
        body=b'{"a":2}',
        signature=f"ts={ts};sig={sig}",
        secret=secret,
        now=ts,
    )


def test_rejects_stale_timestamp():
    secret = "whsec_test"
    ts = 1_700_000_000
    sig = _sign(secret, ts, b'{}')
    assert not verify(
        body=b'{}',
        signature=f"ts={ts};sig={sig}",
        secret=secret,
        now=ts + 600,
        tolerance_seconds=300,
    )


def test_accepts_when_tolerance_disabled():
    secret = "whsec_test"
    ts = 1_700_000_000
    sig = _sign(secret, ts, b'{}')
    assert verify(
        body=b'{}',
        signature=f"ts={ts};sig={sig}",
        secret=secret,
        now=ts + 99_999,
        tolerance_seconds=0,
    )


def test_rejects_malformed_headers():
    body = b'{}'
    secret = "whsec_test"
    for header in ["", "garbage", "ts=abc;sig=def", "ts=1;sig="]:
        assert not verify(body=body, signature=header, secret=secret)
    assert not verify(body=body, signature=None, secret=secret)


def test_accepts_string_body():
    body = '{"event":"environment.updated"}'
    ts = 1_700_000_000
    sig = _sign("whsec_test", ts, body.encode())
    assert verify(
        body=body,
        signature=f"ts={ts};sig={sig}",
        secret="whsec_test",
        now=ts,
    )
