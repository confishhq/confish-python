"""Configuration read/write API."""
from __future__ import annotations

from typing import Any, cast

from ._http import HttpClient


class Config:
    """Wraps the ``/c/{env}`` configuration endpoints."""

    def __init__(self, http: HttpClient, env_id: str) -> None:
        self._http = http
        self._env_id = env_id

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
