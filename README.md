# confish

Official Python SDK for [confish](https://confi.sh) — typed configuration, actions, logs, feeds, and webhook verification.

- One dependency (`httpx`)
- Sync client with typed exceptions and automatic retry on `429`/`5xx`
- Long-running action consumer with `threading.Event` cancellation
- HMAC-SHA256 webhook verification (stdlib only)

## Install

```sh
pip install confish
```

Requires Python 3.10+.

## Quick start

```python
from confish import Confish

client = Confish(
    env_id="a1b2c3d4e5f6",
    api_key="confish_sk_...",
)

config = client.config.fetch()
print(config["site_name"])
```

The methods return `dict[str, Any]`. To add static typing, use `TypedDict` and `cast`:

```python
from typing import TypedDict, cast

class MyConfig(TypedDict):
    site_name: str
    max_upload_mb: int
    maintenance_mode: bool

config = cast(MyConfig, client.config.fetch())
config["maintenance_mode"]  # type-checked as bool
```

Or with Pydantic:

```python
from pydantic import BaseModel

class MyConfig(BaseModel):
    site_name: str
    max_upload_mb: int
    maintenance_mode: bool

config = MyConfig.model_validate(client.config.fetch())
```

## Reading and writing config

```python
# GET /c/{env_id}
config = client.config.fetch()

# PATCH — only listed fields change
client.config.update({"maintenance_mode": True})

# PUT — replaces everything; omitted fields reset to defaults
client.config.replace({
    "site_name": "My App",
    "max_upload_mb": 50,
    "maintenance_mode": False,
})
```

`update` and `replace` return the full updated configuration.

> Write access must be enabled in environment settings before `update` and `replace` will work.

## Feeds

Feeds hold living, externally-keyed state — one item per `external_id`, partitioned per environment. `client.feed(slug)` returns a bound handle; no HTTP happens until you call a method.

```python
jobs = client.feed("jobs")

# Create or replace an item (PUT). Expires after 24 hours.
jobs.set("sitemap-crawl", {"status": "running", "pages": 1204}, ttl=86400)

# Live items, newest first -> list[FeedItem]
for item in jobs.list():
    print(item.external_id, item.data, item.expires_at)

# Idempotent — deleting a missing item succeeds
jobs.delete("sitemap-crawl")

# Replace the whole feed in one request — built for sync-style cron jobs
# pushing their full dataset. Anything absent is DELETED; [] clears the feed.
result = jobs.replace([
    {"external_id": "sitemap-crawl", "data": {"status": "running"}, "ttl": 86400},
    {"external_id": "price-sync", "data": {"status": "queued"}},
])
print(result.created, result.updated, result.deleted)
```

`set` upserts with declarative PUT semantics: the item's data becomes exactly what you pass, and the TTL becomes exactly `ttl`. **Omitting `ttl` makes the item permanent — it clears any TTL set by a previous `set`.** `ttl` is in seconds (1 to 2,592,000 — 30 days); `external_id` is limited to 255 characters.

`replace` applies the same declarative semantics to the whole partition: it's all-or-nothing (duplicate external IDs, exceeding the plan's item cap, or any schema-invalid item raises `ValidationError` with nothing written) and returns a `FeedReplaceResult` with `created`/`updated`/`deleted` counts.

Each `FeedItem` has `id`, `external_id`, `data`, `expires_at` (`None` for permanent items), `created_at`, and `updated_at` (ISO 8601 strings). An unknown feed slug raises `NotFoundError`; a schema mismatch or full feed raises `ValidationError`.

## Logging

```python
client.logs.info("Worker started", {"region": "eu-west-1"})
client.logs.error("Job failed", {"job_id": "abc"})

# Or with an explicit level:
log_id = client.logs.write("info", "User logged in", {"user_id": 123})

# Or in one batched request — each entry takes an optional context and
# ISO 8601 timestamp:
ids = client.logs.write_batch([
    {"level": "info", "message": "Crawl started"},
    {"level": "error", "message": "Fetch failed", "context": {"url": "https://example.com/sitemap.xml"}},
])
```

`write_batch` caps at 100 entries per request — passing more raises `ValueError` before anything is sent, so split larger batches into chunks of 100. An empty list is a no-op that returns `[]`.

Levels: `debug`, `info`, `notice`, `warning`, `error`, `critical`, `alert`, `emergency`. They follow RFC 5424 (syslog), so they map 1:1 onto stdlib `logging` levels.

### Use with the `logging` module

`ConfishHandler` is a stdlib `logging.Handler`, so the log calls you already have become a confish sink — no call sites change:

```python
import logging
from confish import Confish, ConfishHandler

client = Confish(env_id="...", api_key="...")
logging.getLogger().addHandler(ConfishHandler(client))

logging.info("Crawl started", extra={"job_id": "sitemap-2026-07-12"})
logging.error("Checkout probe failed", extra={"region": "eu-west-1"})
```

Records are buffered in memory and shipped by a daemon thread — a log call never blocks on the network and never raises. The buffer flushes once 50 records are queued or every 5 seconds, whichever comes first, batching up to 100 entries per request:

```python
handler = ConfishHandler(
    client,
    level=logging.INFO,   # stdlib threshold — pass logging.DEBUG for everything
    queue_size=1000,      # bounded buffer; overflow drops the oldest records
    flush_at=50,          # flush as soon as this many records are queued...
    flush_interval=5.0,   # ...or after this many seconds, whichever first
    on_error=lambda exc: print(f"confish sink: {exc}"),  # never logged through itself
)
```

What happens automatically:

- `extra={...}` keys become the entry's `context`; values that aren't JSON-serializable fall back to their `repr`. `logger.exception(...)` adds the formatted traceback as `context["exc_info"]`.
- Timestamps are captured when you log (`record.created`), not when the batch is sent.
- Messages are `%`-formatted lazily (`logger.warning("retry %d of %d", 2, 5)`).
- Stdlib levels map by threshold: `DEBUG→debug`, `INFO→info`, `WARNING→warning`, `ERROR→error`, `CRITICAL→critical` (custom numeric levels land on the nearest lower band). The remaining RFC 5424 levels — `notice`, `alert`, `emergency` — have no stdlib equivalent; send those through `client.logs.notice(...)` and friends.
- Delivery is best-effort by design: if the queue overflows or a batch can't be delivered after the client's retries, those records are dropped, counted on `handler.dropped`, and reported to `on_error`. The handler never logs through itself, so a broken sink can't feed itself.
- `handler.flush()` sends everything queued right now; `handler.close()` flushes, stops the thread (bounded by `close_timeout`), and is registered via `atexit` — short-lived crawls and cron jobs don't lose their tail on exit.

## Actions

The action consumer polls for pending actions, acknowledges them, runs your handler, and reports completion or failure — including idempotent skip if another consumer claimed the action first.

```python
import threading
from confish import Confish, Action, SkipAction

client = Confish(env_id="...", api_key="...")
stop = threading.Event()

def handler(action: Action, ctx) -> dict | None:
    if action.type == "place_order":
        ctx.progress("Submitting order", {"params": action.params})
        # ... do work ...
        return {"order_id": "abc123", "filled_price": 66980.0}
    raise RuntimeError(f"Unknown action type: {action.type}")

client.actions.consume(
    handler=handler,
    poll_interval=15.0,    # base — defaults to 15s
    max_poll_interval=60.0, # adaptive backoff cap
    concurrency=2,
    stop=stop,
    on_error=lambda exc, action: print(f"action {action.id}: {exc}"),
)

# To stop, e.g. on signal:
import signal
signal.signal(signal.SIGTERM, lambda *_: stop.set())
```

What happens automatically:
- A returned `dict` becomes the action's `result` on completion.
- Raising any exception fails the action with `{"error": str(exc)}`.
- Raising `SkipAction` leaves the action acknowledged without resolving it.
- A `409 Conflict` on ack is silently skipped — safe to run multiple consumers.
- Setting `stop` halts new work and waits for in-flight handlers to settle.
- After 3 consecutive empty polls the loop doubles its sleep up to `max_poll_interval`, resetting to `poll_interval` the moment any action is processed. Idle consumers make ~240 requests/hour by default.

You can also drive the lifecycle manually:

```python
actions = client.actions.list()
client.actions.ack("action_id")
client.actions.progress("action_id", "closing 3 positions", {"step": 2})
client.actions.complete("action_id", {"order_id": "abc"})
client.actions.fail("action_id", {"error": "timeout"})
```

## Webhook verification

`verify` parses and verifies in one operation: it returns the parsed `WebhookPayload` on success and raises on failure, so the payload you handle is guaranteed to be the exact bytes the signature covers.

```python
from flask import Flask, request, abort
from confish.webhook import verify, WebhookSignatureError, WebhookTimestampError
import os

app = Flask(__name__)

@app.post("/webhook")
def webhook():
    try:
        payload = verify(
            body=request.data,
            signature=request.headers.get("X-Confish-Signature"),
            secret=os.environ["CONFISH_WEBHOOK_SECRET"],
        )
    except WebhookTimestampError:
        abort(401, "stale timestamp")
    except WebhookSignatureError:
        abort(401, "invalid signature")
    # handle payload.event, payload.changes, payload.values ...
    return "", 200
```

`verify` uses constant-time comparison and rejects timestamps older than 5 minutes by default (`WebhookTimestampError`). Pass `tolerance_seconds=0` to disable timestamp checking. Both exceptions subclass `WebhookVerificationError` (itself a `ConfishError`) if you don't need to distinguish them. Always pass the **raw, unparsed body** — re-serializing parsed JSON breaks verification.

## Errors

```python
from confish import (
    AuthError,
    ConfishError,
    ConflictError,
    ForbiddenError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)

try:
    client.config.fetch()
except RateLimitError as e:
    print(f"slow down — retry after {e.retry_after}s")
except ValidationError as e:
    for field, msgs in e.errors.items():
        print(f"{field}: {msgs}")
except ConfishError as e:
    print(f"HTTP {e.status_code}: {e.message}")
```

By default the client retries `429` (honoring `Retry-After`) and `5xx` responses up to twice. Tune with `max_retries` on the `Confish` constructor.

## Options

```python
client = Confish(
    env_id="a1b2c3d4e5f6",
    api_key="confish_sk_...",
    base_url="https://confi.sh",  # override for self-hosted
    user_agent="my-app/1.0",
    max_retries=2,
    max_retry_delay=30.0,
    http_client=None,             # inject your own httpx.Client
)
```

`Confish` is a context manager:

```python
with Confish(env_id="...", api_key="...") as client:
    config = client.config.fetch()
```

## License

MIT
