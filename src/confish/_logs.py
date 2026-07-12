"""Log ingestion API."""
from __future__ import annotations

from typing import Any, cast

from ._http import HttpClient
from ._types import LogLevel

MAX_BATCH_ENTRIES = 100
"""Server-side cap on entries per batch request."""


class Logs:
    """Wraps the ``/c/{env}/log`` and ``/c/{env}/logs`` endpoints, with one convenience method per level."""

    def __init__(self, http: HttpClient, env_id: str) -> None:
        self._http = http
        self._env_id = env_id

    def write(
        self,
        level: LogLevel,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Send a log entry. Returns the new log entry's ID."""
        body: dict[str, Any] = {"level": level, "message": message}
        if context is not None:
            body["context"] = context
        response = self._http.request("POST", f"/c/{self._env_id}/log", body=body)
        return cast(str, response["id"])

    def write_batch(self, entries: list[dict[str, Any]]) -> list[str]:
        """Send up to 100 log entries in one request. Returns the new entry IDs in order.

        Each entry is a dict with ``level`` and ``message``, plus an optional
        ``context`` (dict) and ``timestamp`` (ISO 8601 string; the server
        stamps entries without one at receive time).

        More than 100 entries — the server-side cap per batch request —
        raises :class:`ValueError` without making a request; split the batch
        instead. An empty list sends nothing and returns ``[]``.
        """
        if len(entries) > MAX_BATCH_ENTRIES:
            raise ValueError(
                f"write_batch accepts at most {MAX_BATCH_ENTRIES} entries per request, "
                f"got {len(entries)}"
            )
        if not entries:
            return []
        response = self._http.request(
            "POST", f"/c/{self._env_id}/logs", body={"entries": entries}
        )
        return cast(list[str], response["ids"])

    def debug(self, message: str, context: dict[str, Any] | None = None) -> str:
        return self.write("debug", message, context)

    def info(self, message: str, context: dict[str, Any] | None = None) -> str:
        return self.write("info", message, context)

    def notice(self, message: str, context: dict[str, Any] | None = None) -> str:
        return self.write("notice", message, context)

    def warning(self, message: str, context: dict[str, Any] | None = None) -> str:
        return self.write("warning", message, context)

    def error(self, message: str, context: dict[str, Any] | None = None) -> str:
        return self.write("error", message, context)

    def critical(self, message: str, context: dict[str, Any] | None = None) -> str:
        return self.write("critical", message, context)

    def alert(self, message: str, context: dict[str, Any] | None = None) -> str:
        return self.write("alert", message, context)

    def emergency(self, message: str, context: dict[str, Any] | None = None) -> str:
        return self.write("emergency", message, context)
