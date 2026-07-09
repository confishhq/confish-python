"""Public type aliases and dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

LogLevel = Literal[
    "debug", "info", "notice", "warning", "error", "critical", "alert", "emergency"
]

ActionStatus = Literal[
    "pending", "acknowledged", "completed", "failed", "expired"
]


@dataclass
class ActionUpdate:
    message: str
    data: dict[str, Any] | None = None
    timestamp: str | None = None


@dataclass
class Action:
    """A single action returned by the actions API."""

    id: str
    type: str
    status: ActionStatus
    params: dict[str, Any] | None = None
    updates: list[ActionUpdate] = field(default_factory=list)
    result: dict[str, Any] | None = None
    expires_at: str | None = None
    acknowledged_at: str | None = None
    completed_at: str | None = None
    created_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Action:
        updates = [
            ActionUpdate(
                message=u.get("message", ""),
                data=u.get("data"),
                timestamp=u.get("timestamp"),
            )
            for u in (data.get("updates") or [])
        ]
        return cls(
            id=data["id"],
            type=data["type"],
            status=data["status"],
            params=data.get("params"),
            updates=updates,
            result=data.get("result"),
            expires_at=data.get("expires_at"),
            acknowledged_at=data.get("acknowledged_at"),
            completed_at=data.get("completed_at"),
            created_at=data.get("created_at"),
        )


@dataclass
class FeedItem:
    """A single feed item returned by the feeds API.

    Timestamps are ISO 8601 strings; ``expires_at`` is ``None`` for permanent items.
    """

    id: str
    external_id: str
    data: dict[str, Any]
    expires_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeedItem:
        return cls(
            id=data["id"],
            external_id=data["external_id"],
            data=data.get("data") or {},
            expires_at=data.get("expires_at"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class FeedReplaceResult:
    """Item counts returned by :meth:`~confish.Feed.replace`."""

    created: int
    updated: int
    deleted: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeedReplaceResult:
        return cls(
            created=data["created"],
            updated=data["updated"],
            deleted=data["deleted"],
        )
