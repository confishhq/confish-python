"""Log ingestion API."""
from __future__ import annotations

from typing import Any, cast

from ._http import HttpClient
from ._types import LogLevel


class Logs:
    """Wraps the ``/c/{env}/log`` endpoint, with one convenience method per level."""

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
