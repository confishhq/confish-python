"""Webhook signature verification.

Always pass the raw, unparsed request body to :func:`verify` — re-serializing
parsed JSON alters byte order and breaks signature comparison. On success
:func:`verify` returns the parsed :class:`WebhookPayload`; on failure it raises
:class:`WebhookSignatureError` or :class:`WebhookTimestampError`.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from ._errors import (
    WebhookSignatureError,
    WebhookTimestampError,
    WebhookVerificationError,
)

__all__ = [
    "DEFAULT_TOLERANCE_SECONDS",
    "WebhookPayload",
    "WebhookSignatureError",
    "WebhookTimestampError",
    "WebhookVerificationError",
    "verify",
]

DEFAULT_TOLERANCE_SECONDS = 300

_SIGNATURE_RE = re.compile(r"^ts=(\d+);sig=([a-fA-F0-9]+)$")


@dataclass
class WebhookPayload:
    """A verified, parsed webhook body."""

    event: str
    timestamp: str | None = None
    application: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)
    changes: list[str] | None = None
    values: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WebhookPayload:
        return cls(
            event=data.get("event", ""),
            timestamp=data.get("timestamp"),
            application=data.get("application") or {},
            environment=data.get("environment") or {},
            changes=data.get("changes"),
            values=data.get("values"),
        )


def verify(
    *,
    body: bytes | str,
    signature: str | None,
    secret: str,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    now: float | None = None,
) -> WebhookPayload:
    """Verify a confish webhook signature and return the parsed payload.

    Parsing and verification are one operation: the returned
    :class:`WebhookPayload` is guaranteed to be the exact bytes the signature
    covers. Uses constant-time comparison.

    Raises:
        WebhookSignatureError: The signature is missing, malformed, or doesn't
            match the body.
        WebhookTimestampError: The timestamp is more than ``tolerance_seconds``
            from now (pass ``0`` to disable timestamp checking).
    """
    if not signature or not secret:
        raise WebhookSignatureError("Webhook signature or secret is missing")

    match = _SIGNATURE_RE.match(signature.strip())
    if match is None:
        raise WebhookSignatureError("Webhook signature header is malformed")

    ts_str, provided = match.group(1), match.group(2)
    try:
        ts = int(ts_str)
    except ValueError:
        raise WebhookSignatureError("Webhook signature header is malformed") from None

    # HMAC before tolerance, so WebhookTimestampError always means
    # "authentic but stale" - a forged payload must never report a
    # timestamp problem.
    body_bytes = body.encode() if isinstance(body, str) else body
    expected = hmac.new(
        secret.encode(),
        f"{ts}:".encode() + body_bytes,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(provided, expected):
        raise WebhookSignatureError("Webhook signature does not match the body")

    if tolerance_seconds > 0:
        current = now if now is not None else time.time()
        if abs(int(current) - ts) > tolerance_seconds:
            raise WebhookTimestampError(
                f"Webhook timestamp is outside the {tolerance_seconds}s tolerance window"
            )

    try:
        parsed = json.loads(body_bytes)
    except ValueError as exc:
        raise WebhookVerificationError("Webhook body is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise WebhookVerificationError("Webhook body is not a JSON object")

    return WebhookPayload.from_dict(parsed)
