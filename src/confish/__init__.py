"""Official Python SDK for confish (https://confi.sh)."""
from __future__ import annotations

from ._actions import (
    ActionHandler,
    Actions,
    ActionUpdater,
    SkipAction,
)
from ._client import DEFAULT_BASE_URL, Confish
from ._config import Config
from ._errors import (
    AuthError,
    ConfishError,
    ConflictError,
    ForbiddenError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
    WebhookSignatureError,
    WebhookTimestampError,
    WebhookVerificationError,
)
from ._feeds import Feed
from ._logging import ConfishHandler
from ._logs import Logs
from ._types import Action, ActionStatus, ActionUpdate, FeedItem, FeedReplaceResult, LogLevel

__all__ = [
    "DEFAULT_BASE_URL",
    "Action",
    "ActionHandler",
    "ActionStatus",
    "ActionUpdate",
    "ActionUpdater",
    "Actions",
    "AuthError",
    "Config",
    "Confish",
    "ConfishError",
    "ConfishHandler",
    "ConflictError",
    "Feed",
    "FeedItem",
    "FeedReplaceResult",
    "ForbiddenError",
    "LogLevel",
    "Logs",
    "NetworkError",
    "NotFoundError",
    "RateLimitError",
    "ServerError",
    "SkipAction",
    "ValidationError",
    "WebhookSignatureError",
    "WebhookTimestampError",
    "WebhookVerificationError",
]

__version__ = "0.2.0"
