"""Official Python SDK for confish (https://confi.sh)."""
from __future__ import annotations

from ._actions import (
    ActionHandler,
    Actions,
    ActionUpdater,
    SkipAction,
)
from ._client import DEFAULT_BASE_URL, Confish, Logger
from ._errors import (
    AuthError,
    ConfishError,
    ConflictError,
    ForbiddenError,
    NetworkError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from ._types import Action, ActionStatus, ActionUpdate, LogLevel

__all__ = [
    "DEFAULT_BASE_URL",
    "Action",
    "ActionHandler",
    "ActionStatus",
    "ActionUpdate",
    "ActionUpdater",
    "Actions",
    "AuthError",
    "Confish",
    "ConfishError",
    "ConflictError",
    "ForbiddenError",
    "LogLevel",
    "Logger",
    "NetworkError",
    "RateLimitError",
    "ServerError",
    "SkipAction",
    "ValidationError",
]

__version__ = "0.1.0"
