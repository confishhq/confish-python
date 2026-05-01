"""Main Confish client."""
from __future__ import annotations

from types import TracebackType
from typing import Any, cast

import httpx

from ._actions import Actions
from ._http import HttpClient
from ._types import LogLevel

DEFAULT_BASE_URL = "https://confi.sh"


class Confish:
    """Synchronous client for the confish API.

    Example:
        client = Confish(env_id="...", api_key="...")
        config = client.fetch()  # -> dict[str, Any]

    Use ``cast(MyConfig, client.fetch())`` (with ``MyConfig`` being a ``TypedDict``)
    or ``MyModel.model_validate(client.fetch())`` (with Pydantic) to add typing.
    """

    def __init__(
        self,
        *,
        env_id: str,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        user_agent: str = "confish-python",
        max_retries: int = 2,
        max_retry_delay: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        if not env_id:
            raise ValueError("env_id is required")
        if not api_key:
            raise ValueError("api_key is required")

        self._env_id = env_id
        self._http = HttpClient(
            base_url=base_url,
            api_key=api_key,
            user_agent=user_agent,
            max_retries=max_retries,
            max_retry_delay=max_retry_delay,
            client=http_client,
        )
        self.actions = Actions(self._http, env_id)
        self.logger = Logger(self)

    def __enter__(self) -> Confish:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def fetch(self) -> dict[str, Any]:
        """Fetch the environment's configuration values."""
        return cast(dict[str, Any], self._http.request("GET", f"/c/{self._env_id}"))

    def update(self, values: dict[str, Any]) -> dict[str, Any]:
        """Partially update configuration values (PATCH). Returns the full updated config."""
        return cast(
            dict[str, Any],
            self._http.request("PATCH", f"/c/{self._env_id}", body={"values": values}),
        )

    def replace(self, values: dict[str, Any]) -> dict[str, Any]:
        """Replace all configuration values (PUT). Omitted fields reset to defaults."""
        return cast(
            dict[str, Any],
            self._http.request("PUT", f"/c/{self._env_id}", body={"values": values}),
        )

    def log(
        self,
        *,
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


class Logger:
    """Convenience wrapper around ``Confish.log`` with one method per level."""

    def __init__(self, client: Confish) -> None:
        self._client = client

    def debug(self, message: str, context: dict[str, Any] | None = None) -> str:
        return self._client.log(level="debug", message=message, context=context)

    def info(self, message: str, context: dict[str, Any] | None = None) -> str:
        return self._client.log(level="info", message=message, context=context)

    def notice(self, message: str, context: dict[str, Any] | None = None) -> str:
        return self._client.log(level="notice", message=message, context=context)

    def warning(self, message: str, context: dict[str, Any] | None = None) -> str:
        return self._client.log(level="warning", message=message, context=context)

    def error(self, message: str, context: dict[str, Any] | None = None) -> str:
        return self._client.log(level="error", message=message, context=context)

    def critical(self, message: str, context: dict[str, Any] | None = None) -> str:
        return self._client.log(level="critical", message=message, context=context)

    def alert(self, message: str, context: dict[str, Any] | None = None) -> str:
        return self._client.log(level="alert", message=message, context=context)
