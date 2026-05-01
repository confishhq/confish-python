"""Internal HTTP transport with retries."""
from __future__ import annotations

import time
from typing import Any

import httpx

from ._errors import (
    ConfishError,
    NetworkError,
    RateLimitError,
    ServerError,
    error_from_response,
)


class HttpClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        user_agent: str,
        max_retries: int,
        max_retry_delay: float,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._user_agent = user_agent
        self._max_retries = max_retries
        self._max_retry_delay = max_retry_delay
        self._client = client or httpx.Client(timeout=30.0)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "User-Agent": self._user_agent,
        }
        kwargs: dict[str, Any] = {"headers": headers}
        if body is not None:
            kwargs["json"] = body

        attempt = 0
        while True:
            try:
                response = self._client.request(method, url, **kwargs)
            except httpx.RequestError as exc:
                raise NetworkError(
                    f"Network request to {url} failed: {exc}", cause=exc
                ) from exc

            if 200 <= response.status_code < 300:
                if not response.content:
                    return None
                try:
                    return response.json()
                except ValueError as exc:
                    raise ConfishError(
                        "Failed to parse response body as JSON",
                        status_code=response.status_code,
                        body=response.text,
                    ) from exc

            try:
                payload: Any = response.json() if response.content else None
            except ValueError:
                payload = response.text or None

            err = error_from_response(
                response.status_code, payload, dict(response.headers)
            )

            if not self._should_retry(attempt, err):
                raise err

            time.sleep(self._retry_delay(attempt, err))
            attempt += 1

    def _should_retry(self, attempt: int, err: ConfishError) -> bool:
        if attempt >= self._max_retries:
            return False
        return isinstance(err, RateLimitError | ServerError)

    def _retry_delay(self, attempt: int, err: ConfishError) -> float:
        if isinstance(err, RateLimitError) and err.retry_after is not None:
            return min(float(err.retry_after), self._max_retry_delay)
        return float(min(2 ** attempt, self._max_retry_delay))
