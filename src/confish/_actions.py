"""Actions API and consumer loop."""
from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Protocol

from ._errors import ConflictError
from ._http import HttpClient
from ._types import Action


class ActionUpdater(Protocol):
    """Passed to handlers so they can append timeline updates."""

    def update(
        self, message: str, data: dict[str, Any] | None = None
    ) -> Action: ...


ActionHandler = Callable[[Action, ActionUpdater], "dict[str, Any] | None"]


class _SkipAction(Exception):  # noqa: N818  control-flow signal, not an error
    """Raised inside a handler to leave the action acknowledged without resolving it."""


SkipAction = _SkipAction
"""Raise inside an action handler to leave the action acknowledged without
completing or failing it. The action will stay acknowledged until it expires."""


class Actions:
    """Wraps the ``/c/{env}/actions`` endpoints."""

    def __init__(self, http: HttpClient, env_id: str) -> None:
        self._http = http
        self._env_id = env_id

    def list(self) -> list[Action]:
        """Return pending, non-expired actions ordered oldest first."""
        response = self._http.request("GET", f"/c/{self._env_id}/actions")
        return [Action.from_dict(a) for a in response.get("actions", [])]

    def ack(self, action_id: str) -> Action:
        """Acknowledge an action. Raises ConflictError if no longer actionable."""
        response = self._http.request(
            "POST", f"/c/{self._env_id}/actions/{action_id}/ack"
        )
        return Action.from_dict(response)

    def update(
        self, action_id: str, message: str, data: dict[str, Any] | None = None
    ) -> Action:
        """Append a timeline update visible in the dashboard."""
        body: dict[str, Any] = {"message": message}
        if data is not None:
            body["data"] = data
        response = self._http.request(
            "POST", f"/c/{self._env_id}/actions/{action_id}/update", body=body
        )
        return Action.from_dict(response)

    def complete(
        self, action_id: str, result: dict[str, Any] | None = None
    ) -> Action:
        """Mark the action as completed."""
        body: dict[str, Any] = {}
        if result is not None:
            body["result"] = result
        response = self._http.request(
            "POST", f"/c/{self._env_id}/actions/{action_id}/complete", body=body
        )
        return Action.from_dict(response)

    def fail(
        self, action_id: str, result: dict[str, Any] | None = None
    ) -> Action:
        """Mark the action as failed."""
        body: dict[str, Any] = {}
        if result is not None:
            body["result"] = result
        response = self._http.request(
            "POST", f"/c/{self._env_id}/actions/{action_id}/fail", body=body
        )
        return Action.from_dict(response)

    def consume(
        self,
        handler: ActionHandler,
        *,
        poll_interval: float = 15.0,
        max_poll_interval: float = 60.0,
        concurrency: int = 1,
        stop: threading.Event | None = None,
        on_error: Callable[[BaseException, Action], None] | None = None,
    ) -> None:
        """Long-running consumer loop.

        Polls for pending actions, acknowledges them, runs ``handler``, and reports
        completion or failure based on the handler's outcome. Returning a dict
        becomes the action's ``result`` on completion. Raising fails the action with
        ``{"error": str(exc)}``. Raising :data:`SkipAction` leaves the action
        acknowledged without resolving it.

        After 3 consecutive empty polls the sleep doubles each poll up to
        ``max_poll_interval``, resetting to ``poll_interval`` the moment any action
        is processed. Pass a :class:`threading.Event` and call ``set()`` to stop.
        """
        if poll_interval <= 0:
            poll_interval = 15.0
        if max_poll_interval <= 0:
            max_poll_interval = 60.0
        concurrency = max(1, concurrency)
        stop = stop or threading.Event()

        executor = ThreadPoolExecutor(max_workers=concurrency)
        in_flight: set[Future[None]] = set()
        empty_polls = 0

        try:
            while not stop.is_set():
                try:
                    actions = self.list()
                except Exception as exc:
                    if on_error is not None:
                        on_error(exc, Action(id="", type="", status="pending"))
                    if stop.wait(_backoff_delay(empty_polls, poll_interval, max_poll_interval)):
                        break
                    continue

                pending = [a for a in actions if a.status == "pending"]
                if not pending:
                    empty_polls += 1
                    if stop.wait(_backoff_delay(empty_polls, poll_interval, max_poll_interval)):
                        break
                    continue

                empty_polls = 0
                for action in pending:
                    if stop.is_set():
                        break
                    while len(in_flight) >= concurrency:
                        _await_one(in_flight)
                    future = executor.submit(
                        self._process_action, action, handler, on_error, stop
                    )
                    in_flight.add(future)
                    future.add_done_callback(in_flight.discard)
        finally:
            for future in list(in_flight):
                future.result()
            executor.shutdown(wait=True)

    def _process_action(
        self,
        action: Action,
        handler: ActionHandler,
        on_error: Callable[[BaseException, Action], None] | None,
        stop: threading.Event,
    ) -> None:
        try:
            self.ack(action.id)
        except ConflictError:
            return
        except Exception as exc:
            if on_error is not None:
                on_error(exc, action)
            return

        updater = _Updater(self, action.id)

        try:
            result = handler(action, updater)
        except _SkipAction:
            return
        except Exception as exc:
            if on_error is not None:
                on_error(exc, action)
            if stop.is_set():
                return
            try:
                self.fail(action.id, {"error": str(exc)})
            except Exception as fail_exc:
                if on_error is not None:
                    on_error(fail_exc, action)
            return

        if stop.is_set():
            return
        try:
            self.complete(action.id, result if isinstance(result, dict) else None)
        except Exception as exc:
            if on_error is not None:
                on_error(exc, action)


class _Updater:
    def __init__(self, actions: Actions, action_id: str) -> None:
        self._actions = actions
        self._action_id = action_id

    def update(
        self, message: str, data: dict[str, Any] | None = None
    ) -> Action:
        return self._actions.update(self._action_id, message, data)


def _backoff_delay(empty_polls: int, base: float, maximum: float) -> float:
    if empty_polls <= 3:
        return base
    return float(min(base * (2 ** (empty_polls - 3)), maximum))


def _await_one(futures: set[Future[None]]) -> None:
    """Block until at least one future in the set finishes."""
    if not futures:
        return
    done = next(iter(futures))
    for fut in futures:
        if fut.done():
            done = fut
            break
    done.result()
