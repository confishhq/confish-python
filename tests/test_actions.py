from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from confish import Action, Confish, SkipAction


def _pending(action_id: str = "a1") -> dict[str, Any]:
    return {
        "id": action_id,
        "type": "noop",
        "status": "pending",
        "params": None,
        "updates": [],
        "result": None,
        "expires_at": None,
        "acknowledged_at": None,
        "completed_at": None,
        "created_at": None,
    }


def test_list_unwraps_actions_array(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test/actions",
        method="GET",
        json={"actions": [_pending("a1"), _pending("a2")]},
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")
    actions = client.actions.list()
    assert len(actions) == 2
    assert actions[0].id == "a1"
    assert isinstance(actions[0], Action)


def test_complete_with_result(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test/actions/a1/complete",
        method="POST",
        json=_pending("a1"),
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")
    client.actions.complete("a1", {"order_id": "abc"})

    import json
    body = json.loads(httpx_mock.get_request().content)
    assert body == {"result": {"order_id": "abc"}}


def test_complete_without_result(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test/actions/a1/complete",
        method="POST",
        json=_pending("a1"),
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")
    client.actions.complete("a1")

    import json
    body = json.loads(httpx_mock.get_request().content)
    assert body == {}


@pytest.mark.httpx_mock(assert_all_responses_were_requested=False)
def test_consume_processes_action(httpx_mock):
    # First poll returns one action; subsequent polls return empty.
    httpx_mock.add_response(
        url="https://api.test/c/env_test/actions",
        method="GET",
        json={"actions": [_pending("a1")]},
    )
    httpx_mock.add_response(
        url="https://api.test/c/env_test/actions",
        method="GET",
        json={"actions": []},
        is_reusable=True,
    )
    httpx_mock.add_response(
        url="https://api.test/c/env_test/actions/a1/ack",
        method="POST",
        json=_pending("a1"),
    )
    httpx_mock.add_response(
        url="https://api.test/c/env_test/actions/a1/complete",
        method="POST",
        json=_pending("a1"),
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")

    stop = threading.Event()
    received: list[Action] = []

    def handler(action: Action, ctx: Any) -> dict[str, Any]:
        received.append(action)
        return {"filled": True}

    thread = threading.Thread(
        target=client.actions.consume,
        kwargs={"handler": handler, "poll_interval": 0.01, "stop": stop},
    )
    thread.start()
    deadline = time.time() + 2
    while time.time() < deadline:
        if any(r.method == "POST" and r.url.path.endswith("/complete") for r in httpx_mock.get_requests()):
            break
        time.sleep(0.01)
    stop.set()
    thread.join(timeout=2)

    assert received and received[0].id == "a1"
    complete_request = next(
        r for r in httpx_mock.get_requests()
        if r.method == "POST" and r.url.path.endswith("/complete")
    )
    import json
    assert json.loads(complete_request.content) == {"result": {"filled": True}}


@pytest.mark.httpx_mock(assert_all_responses_were_requested=False)
def test_consume_fails_on_handler_exception(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test/actions",
        method="GET",
        json={"actions": [_pending("a1")]},
    )
    httpx_mock.add_response(
        url="https://api.test/c/env_test/actions",
        method="GET",
        json={"actions": []},
        is_reusable=True,
    )
    httpx_mock.add_response(
        url="https://api.test/c/env_test/actions/a1/ack",
        method="POST",
        json=_pending("a1"),
    )
    httpx_mock.add_response(
        url="https://api.test/c/env_test/actions/a1/fail",
        method="POST",
        json=_pending("a1"),
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")

    stop = threading.Event()

    def handler(action: Action, ctx: Any) -> None:
        raise RuntimeError("boom")

    thread = threading.Thread(
        target=client.actions.consume,
        kwargs={"handler": handler, "poll_interval": 0.01, "stop": stop},
    )
    thread.start()
    deadline = time.time() + 2
    while time.time() < deadline:
        if any(r.method == "POST" and r.url.path.endswith("/fail") for r in httpx_mock.get_requests()):
            break
        time.sleep(0.01)
    stop.set()
    thread.join(timeout=2)

    fail_request = next(
        r for r in httpx_mock.get_requests()
        if r.method == "POST" and r.url.path.endswith("/fail")
    )
    import json
    assert json.loads(fail_request.content) == {"result": {"error": "boom"}}


@pytest.mark.httpx_mock(assert_all_responses_were_requested=False)
def test_consume_skips_on_409_ack(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test/actions",
        method="GET",
        json={"actions": [_pending("a1")]},
    )
    httpx_mock.add_response(
        url="https://api.test/c/env_test/actions",
        method="GET",
        json={"actions": []},
        is_reusable=True,
    )
    httpx_mock.add_response(
        url="https://api.test/c/env_test/actions/a1/ack",
        method="POST",
        status_code=409,
        json={"error": "already acknowledged"},
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")

    stop = threading.Event()
    handler_ran = threading.Event()

    def handler(action: Action, ctx: Any) -> None:
        handler_ran.set()

    thread = threading.Thread(
        target=client.actions.consume,
        kwargs={"handler": handler, "poll_interval": 0.01, "stop": stop},
    )
    thread.start()
    time.sleep(0.1)
    stop.set()
    thread.join(timeout=2)

    assert not handler_ran.is_set()


@pytest.mark.httpx_mock(assert_all_responses_were_requested=False)
def test_skip_action_keeps_action_acknowledged(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test/actions",
        method="GET",
        json={"actions": [_pending("a1")]},
    )
    httpx_mock.add_response(
        url="https://api.test/c/env_test/actions",
        method="GET",
        json={"actions": []},
        is_reusable=True,
    )
    httpx_mock.add_response(
        url="https://api.test/c/env_test/actions/a1/ack",
        method="POST",
        json=_pending("a1"),
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")

    stop = threading.Event()

    def handler(action: Action, ctx: Any) -> None:
        raise SkipAction()

    thread = threading.Thread(
        target=client.actions.consume,
        kwargs={"handler": handler, "poll_interval": 0.01, "stop": stop},
    )
    thread.start()
    time.sleep(0.1)
    stop.set()
    thread.join(timeout=2)

    paths = [r.url.path for r in httpx_mock.get_requests() if r.method == "POST"]
    assert all(not p.endswith(("/complete", "/fail")) for p in paths)
