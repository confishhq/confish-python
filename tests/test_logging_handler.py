from __future__ import annotations

import datetime as dt
import json
import logging
import threading
import time
from typing import Any

import httpx
import pytest

from confish import Confish, ConfishHandler, NetworkError

LOGS_URL = "https://api.test/c/env_test/logs"


def _entries(request: httpx.Request) -> list[dict[str, Any]]:
    return json.loads(request.content)["entries"]


def _wait_for_requests(httpx_mock, count: int = 1, timeout: float = 2.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(httpx_mock.get_requests()) >= count:
            return
        time.sleep(0.01)


@pytest.fixture
def make_handler(request):
    """Yield a factory building a (logger, handler) pair; tears everything down."""
    created: list[tuple[logging.Logger, ConfishHandler, Confish]] = []

    def factory(**kwargs: Any) -> tuple[logging.Logger, ConfishHandler]:
        client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")
        # Defaults that keep tests deterministic; individual tests override.
        options: dict[str, Any] = {
            "level": logging.DEBUG,
            "flush_at": 1000,
            "flush_interval": 60.0,
        }
        options.update(kwargs)
        handler = ConfishHandler(client, **options)
        logger = logging.getLogger(f"confish-test-{request.node.name}")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        logger.addHandler(handler)
        created.append((logger, handler, client))
        return logger, handler

    yield factory

    for logger, handler, client in created:
        logger.removeHandler(handler)
        handler.close()
        client.close()


def test_stdlib_levels_map_to_confish_levels(httpx_mock, make_handler):
    httpx_mock.add_response(url=LOGS_URL, method="POST", json={"ids": []})
    logger, handler = make_handler()

    logger.debug("d")
    logger.info("i")
    logger.warning("w")
    logger.error("e")
    logger.critical("c")
    handler.flush()

    entries = _entries(httpx_mock.get_request())
    assert [(e["level"], e["message"]) for e in entries] == [
        ("debug", "d"),
        ("info", "i"),
        ("warning", "w"),
        ("error", "e"),
        ("critical", "c"),
    ]


def test_custom_numeric_levels_map_by_threshold(httpx_mock, make_handler):
    httpx_mock.add_response(url=LOGS_URL, method="POST", json={"ids": []})
    logger, handler = make_handler(level=1)
    logger.setLevel(1)

    logger.log(5, "below debug")
    logger.log(25, "between info and warning")
    logger.log(35, "between warning and error")
    logger.log(60, "above critical")
    handler.flush()

    entries = _entries(httpx_mock.get_request())
    assert [e["level"] for e in entries] == ["debug", "info", "warning", "critical"]


def test_extra_becomes_context_without_standard_attrs(httpx_mock, make_handler):
    httpx_mock.add_response(url=LOGS_URL, method="POST", json={"ids": []})
    logger, handler = make_handler()

    logger.info("crawl finished", extra={"job_id": "sitemap-crawl", "pages": 1204})
    handler.flush()

    (entry,) = _entries(httpx_mock.get_request())
    assert entry["context"] == {"job_id": "sitemap-crawl", "pages": 1204}


def test_entry_omits_context_when_no_extras(httpx_mock, make_handler):
    httpx_mock.add_response(url=LOGS_URL, method="POST", json={"ids": []})
    logger, handler = make_handler()

    logger.info("no extras here")
    handler.flush()

    (entry,) = _entries(httpx_mock.get_request())
    assert "context" not in entry


def test_non_json_extra_values_fall_back_to_repr(httpx_mock, make_handler):
    httpx_mock.add_response(url=LOGS_URL, method="POST", json={"ids": []})
    logger, handler = make_handler()

    moment = dt.datetime(2026, 7, 12, 8, 30, tzinfo=dt.timezone.utc)
    logger.info("scheduled", extra={"when": moment, "attempt": 1})
    handler.flush()

    (entry,) = _entries(httpx_mock.get_request())
    assert entry["context"] == {"when": repr(moment), "attempt": 1}


def test_message_is_lazily_formatted(httpx_mock, make_handler):
    httpx_mock.add_response(url=LOGS_URL, method="POST", json={"ids": []})
    logger, handler = make_handler()

    logger.warning("retry %d of %d", 2, 5)
    handler.flush()

    (entry,) = _entries(httpx_mock.get_request())
    assert entry["message"] == "retry 2 of 5"


def test_exc_info_is_formatted_into_context(httpx_mock, make_handler):
    httpx_mock.add_response(url=LOGS_URL, method="POST", json={"ids": []})
    logger, handler = make_handler()

    try:
        raise ValueError("bad checksum")
    except ValueError:
        logger.exception("incident while parsing feed")
    handler.flush()

    (entry,) = _entries(httpx_mock.get_request())
    assert entry["level"] == "error"
    assert entry["message"] == "incident while parsing feed"
    assert "Traceback" in entry["context"]["exc_info"]
    assert "ValueError: bad checksum" in entry["context"]["exc_info"]


def test_timestamp_is_captured_at_log_time(httpx_mock, make_handler):
    httpx_mock.add_response(url=LOGS_URL, method="POST", json={"ids": []})
    logger, handler = make_handler()

    captured: list[logging.LogRecord] = []

    def capture(record: logging.LogRecord) -> bool:
        captured.append(record)
        return True

    logger.addFilter(capture)
    logger.info("stamped")
    logger.removeFilter(capture)
    time.sleep(0.05)  # entry sits in the queue before flushing
    handler.flush()

    (entry,) = _entries(httpx_mock.get_request())
    expected = dt.datetime.fromtimestamp(captured[0].created, tz=dt.timezone.utc)
    assert entry["timestamp"] == expected.isoformat()


def test_flushes_when_flush_at_reached(httpx_mock, make_handler):
    httpx_mock.add_response(url=LOGS_URL, method="POST", json={"ids": []})
    logger, _handler = make_handler(flush_at=3, flush_interval=60.0)

    logger.info("one")
    logger.info("two")
    logger.info("three")

    _wait_for_requests(httpx_mock)
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    assert [e["message"] for e in _entries(requests[0])] == ["one", "two", "three"]


def test_flushes_on_interval(httpx_mock, make_handler):
    httpx_mock.add_response(url=LOGS_URL, method="POST", json={"ids": []})
    logger, _handler = make_handler(flush_at=50, flush_interval=0.05)

    logger.info("lonely entry")

    _wait_for_requests(httpx_mock)
    requests = httpx_mock.get_requests()
    assert len(requests) >= 1
    assert [e["message"] for e in _entries(requests[0])] == ["lonely entry"]


def test_flush_chunks_to_max_batch_size(httpx_mock, make_handler):
    httpx_mock.add_response(url=LOGS_URL, method="POST", json={"ids": []}, is_reusable=True)
    logger, handler = make_handler()

    for i in range(250):
        logger.info("entry %d", i)
    handler.flush()

    requests = httpx_mock.get_requests()
    assert [len(_entries(r)) for r in requests] == [100, 100, 50]
    assert _entries(requests[0])[0]["message"] == "entry 0"
    assert _entries(requests[2])[-1]["message"] == "entry 249"


def test_overflow_drops_oldest_and_counts(httpx_mock, make_handler):
    httpx_mock.add_response(url=LOGS_URL, method="POST", json={"ids": []})
    logger, handler = make_handler(queue_size=5)

    for i in range(7):
        logger.info("m%d", i)
    assert handler.dropped == 2
    handler.flush()

    (request,) = httpx_mock.get_requests()
    assert [e["message"] for e in _entries(request)] == ["m2", "m3", "m4", "m5", "m6"]


def test_emit_never_raises_on_bad_format_args(make_handler):
    logger, handler = make_handler()

    logger.info("oops %s %s", "only-one-arg")  # getMessage() raises TypeError

    assert handler.dropped == 1
    handler.flush()  # queue is empty — no request, no error


def test_send_failure_counts_drops_and_reports(httpx_mock, make_handler):
    httpx_mock.add_exception(httpx.ConnectError("boom"), is_reusable=True)
    errors: list[BaseException] = []
    logger, handler = make_handler(on_error=errors.append)

    logger.info("one")
    logger.info("two")
    handler.flush()  # must not raise

    assert handler.dropped == 2
    assert errors and isinstance(errors[0], NetworkError)


def test_on_error_exceptions_are_swallowed(httpx_mock, make_handler):
    httpx_mock.add_exception(httpx.ConnectError("boom"), is_reusable=True)

    def explode(exc: BaseException) -> None:
        raise RuntimeError("callback bug")

    logger, handler = make_handler(on_error=explode)

    logger.info("one")
    handler.flush()  # must not raise despite transport AND callback failing

    assert handler.dropped == 1


def test_close_flushes_remaining_entries(httpx_mock, make_handler):
    httpx_mock.add_response(url=LOGS_URL, method="POST", json={"ids": []})
    logger, handler = make_handler()

    logger.info("almost lost")
    logger.info("me too")
    handler.close()

    (request,) = httpx_mock.get_requests()
    assert [e["message"] for e in _entries(request)] == ["almost lost", "me too"]

    handler.close()  # idempotent
    logger.info("after close")  # dropped, not sent
    assert handler.dropped == 1
    assert len(httpx_mock.get_requests()) == 1


def test_thread_safety_smoke(httpx_mock, make_handler):
    httpx_mock.add_response(url=LOGS_URL, method="POST", json={"ids": []}, is_reusable=True)
    logger, handler = make_handler(flush_at=25, flush_interval=0.01)

    def worker(worker_id: int) -> None:
        for i in range(50):
            logger.info("w%d-%d", worker_id, i)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    handler.close()

    requests = httpx_mock.get_requests()
    sizes = [len(_entries(r)) for r in requests]
    assert all(size <= 100 for size in sizes)
    assert handler.dropped == 0
    assert sum(sizes) == 400
