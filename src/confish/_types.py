"""Public type aliases and dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

LogLevel = Literal[
    "debug", "info", "notice", "warning", "error", "critical", "alert"
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
