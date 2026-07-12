"""Stdlib ``logging`` adapter that ships records to confish in the background."""
from __future__ import annotations

import atexit
import contextlib
import json
import logging
import threading
from collections import deque
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from ._logs import MAX_BATCH_ENTRIES
from ._types import LogLevel

if TYPE_CHECKING:
    from ._client import Confish

_STANDARD_ATTRS: frozenset[str] = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"asctime", "message"}
"""Attributes every ``LogRecord`` carries; anything else came from ``extra={...}``."""

_EXC_FORMATTER = logging.Formatter()


class ConfishHandler(logging.Handler):
    """A ``logging.Handler`` that buffers records and ships them to confish.

    Records are queued in a bounded in-memory buffer (default 1000 entries)
    and sent by a daemon thread once ``flush_at`` records are queued or every
    ``flush_interval`` seconds, whichever comes first, chunked to at most 100
    entries per request. ``emit`` never raises and never blocks on network
    I/O; when the queue overflows the oldest records are dropped and counted
    on :attr:`dropped`. Send failures are counted there too and reported to
    ``on_error`` when provided.

    Wire-up::

        logging.getLogger().addHandler(ConfishHandler(client))

    Stdlib levels map by threshold: ``DEBUG→debug``, ``INFO→info``,
    ``WARNING→warning``, ``ERROR→error``, ``CRITICAL→critical``. The
    remaining RFC 5424 levels (``notice``, ``alert``, ``emergency``) have no
    stdlib equivalent — send those through ``client.logs`` directly.
    """

    def __init__(
        self,
        client: Confish,
        level: int = logging.INFO,
        *,
        queue_size: int = 1000,
        flush_at: int = 50,
        flush_interval: float = 5.0,
        close_timeout: float = 5.0,
        on_error: Callable[[BaseException], None] | None = None,
    ) -> None:
        super().__init__(level)
        if queue_size <= 0:
            raise ValueError("queue_size must be positive")
        if flush_at <= 0:
            raise ValueError("flush_at must be positive")
        if flush_interval <= 0:
            raise ValueError("flush_interval must be positive")

        self._client = client
        self._queue_size = queue_size
        self._flush_at = flush_at
        self._flush_interval = flush_interval
        self._close_timeout = close_timeout
        self._on_error = on_error

        self._queue: deque[dict[str, Any]] = deque()
        self._queue_lock = threading.Lock()
        self._dropped = 0
        self._wake = threading.Event()
        self._shutdown = threading.Event()
        self._sending = threading.local()
        self._thread = threading.Thread(
            target=self._run, name="confish-log-flusher", daemon=True
        )
        self._thread.start()
        atexit.register(self.close)

    @property
    def dropped(self) -> int:
        """Number of records lost to queue overflow or failed sends."""
        with self._queue_lock:
            return self._dropped

    def emit(self, record: logging.LogRecord) -> None:
        """Queue the record for the background flusher. Never raises."""
        if getattr(self._sending, "active", False):
            # A send on this thread produced a record (e.g. the HTTP client's
            # own logging). Shipping it would feed the adapter its own output.
            return
        try:
            entry = self._entry_from_record(record)
        except Exception as exc:
            self._count_drops(1, exc)
            return
        try:
            with self._queue_lock:
                if self._shutdown.is_set():
                    self._dropped += 1
                    return
                if len(self._queue) >= self._queue_size:
                    self._queue.popleft()
                    self._dropped += 1
                self._queue.append(entry)
                wake = len(self._queue) >= self._flush_at
            if wake:
                self._wake.set()
        except Exception as exc:
            self._count_drops(1, exc)

    def flush(self) -> None:
        """Send everything queued right now, from the calling thread. Never raises."""
        self._drain()

    def close(self) -> None:
        """Flush remaining records, stop the background thread, and close the handler.

        Joins the flusher thread with a bounded timeout (``close_timeout``),
        then drains anything it didn't get to. Idempotent; also registered
        via ``atexit`` so process exit flushes the tail.
        """
        if not self._shutdown.is_set():
            self._shutdown.set()
            self._wake.set()
            self._thread.join(timeout=self._close_timeout)
            self._drain()
            with contextlib.suppress(Exception):
                atexit.unregister(self.close)
        super().close()

    def _run(self) -> None:
        while True:
            self._wake.wait(timeout=self._flush_interval)
            self._wake.clear()
            closing = self._shutdown.is_set()
            self._drain()
            if closing:
                return

    def _drain(self) -> None:
        while True:
            with self._queue_lock:
                if not self._queue:
                    return
                chunk = [
                    self._queue.popleft()
                    for _ in range(min(len(self._queue), MAX_BATCH_ENTRIES))
                ]
            self._send(chunk)

    def _send(self, chunk: list[dict[str, Any]]) -> None:
        self._sending.active = True
        try:
            self._client.logs.write_batch(chunk)
        except Exception as exc:
            self._count_drops(len(chunk), exc)
        finally:
            self._sending.active = False

    def _count_drops(self, count: int, exc: BaseException | None = None) -> None:
        with self._queue_lock:
            self._dropped += count
        if exc is not None and self._on_error is not None:
            with contextlib.suppress(Exception):
                self._on_error(exc)

    def _entry_from_record(self, record: logging.LogRecord) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "level": _level_from_levelno(record.levelno),
            "message": record.getMessage(),
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
        }
        context = {
            key: _json_safe(value)
            for key, value in record.__dict__.items()
            if key not in _STANDARD_ATTRS
        }
        if record.exc_info and record.exc_info[0] is not None:
            context["exc_info"] = _EXC_FORMATTER.formatException(record.exc_info)
        if context:
            entry["context"] = context
        return entry


def _level_from_levelno(levelno: int) -> LogLevel:
    if levelno >= logging.CRITICAL:
        return "critical"
    if levelno >= logging.ERROR:
        return "error"
    if levelno >= logging.WARNING:
        return "warning"
    if levelno >= logging.INFO:
        return "info"
    return "debug"


def _json_safe(value: Any) -> Any:
    """Return ``value`` unchanged when JSON-serializable, else its ``repr``."""
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return repr(value)
    return value
