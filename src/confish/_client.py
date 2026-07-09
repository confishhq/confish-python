"""Main Confish client."""
from __future__ import annotations

from types import TracebackType

import httpx

from ._actions import Actions
from ._config import Config
from ._feeds import Feed
from ._http import HttpClient
from ._logs import Logs

DEFAULT_BASE_URL = "https://confi.sh"


class Confish:
    """Synchronous client for the confish API.

    Example:
        client = Confish(env_id="...", api_key="...")
        config = client.config.fetch()  # -> dict[str, Any]

    Use ``cast(MyConfig, client.config.fetch())`` (with ``MyConfig`` being a
    ``TypedDict``) or ``MyModel.model_validate(client.config.fetch())`` (with
    Pydantic) to add typing.
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
        self.config = Config(self._http, env_id)
        self.actions = Actions(self._http, env_id)
        self.logs = Logs(self._http, env_id)

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

    def feed(self, slug: str) -> Feed:
        """Return a handle bound to the feed with the given slug.

        Constructing the handle performs no HTTP; an unknown slug surfaces as
        :class:`~confish.NotFoundError` when a method is called.
        """
        return Feed(self._http, self._env_id, slug)
