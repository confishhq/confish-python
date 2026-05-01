"""Webhook signature verification.

Always pass the raw, unparsed request body to :func:`verify` — re-serializing
parsed JSON alters byte order and breaks signature comparison.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time

DEFAULT_TOLERANCE_SECONDS = 300

_SIGNATURE_RE = re.compile(r"^ts=(\d+);sig=([a-fA-F0-9]+)$")


def verify(
    *,
    body: bytes | str,
    signature: str | None,
    secret: str,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now: float | None = None,
) -> bool:
    """Verify a confish webhook signature.

    Returns ``True`` only if the signature matches **and** the timestamp is within
    ``tolerance_seconds`` of now (pass ``0`` to disable timestamp checking).
    Uses constant-time comparison.
    """
    if not signature or not secret:
        return False

    match = _SIGNATURE_RE.match(signature.strip())
    if match is None:
        return False

    ts_str, provided = match.group(1), match.group(2)
    try:
        ts = int(ts_str)
    except ValueError:
        return False

    if tolerance_seconds > 0:
        current = now if now is not None else time.time()
        if abs(int(current) - ts) > tolerance_seconds:
            return False

    body_bytes = body.encode() if isinstance(body, str) else body
    expected = hmac.new(
        secret.encode(),
        f"{ts}:".encode() + body_bytes,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(provided, expected)
