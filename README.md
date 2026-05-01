# confish

Official Python SDK for [confish](https://confi.sh) — typed configuration, actions, and webhook verification.

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

config = client.fetch()
print(config["site_name"])
```

The methods return `dict[str, Any]`. To add static typing, use `TypedDict` and `cast`:

```python
from typing import TypedDict, cast

class MyConfig(TypedDict):
    site_name: str
    max_upload_mb: int
    maintenance_mode: bool

config = cast(MyConfig, client.fetch())
config["maintenance_mode"]  # type-checked as bool
```

Or with Pydantic:

```python
from pydantic import BaseModel

class MyConfig(BaseModel):
    site_name: str
    max_upload_mb: int
    maintenance_mode: bool

config = MyConfig.model_validate(client.fetch())
```

## Reading and writing config

```python
# GET /c/{env_id}
config = client.fetch()

# PATCH — only listed fields change
client.update({"maintenance_mode": True})

# PUT — replaces everything; omitted fields reset to defaults
client.replace({
    "site_name": "My App",
    "max_upload_mb": 50,
    "maintenance_mode": False,
})
```

`update` and `replace` return the full updated configuration.

> Write access must be enabled in environment settings before `update` and `replace` will work.

## Logging

```python
client.logger.info("Worker started", {"region": "eu-west-1"})
client.logger.error("Job failed", {"job_id": "abc"})

# Or directly:
log_id = client.log(level="info", message="User logged in", context={"user_id": 123})
```

Levels: `debug`, `info`, `notice`, `warning`, `error`, `critical`, `alert`.

## Actions

The action consumer polls for pending actions, acknowledges them, runs your handler, and reports completion or failure — including idempotent skip if another consumer claimed the action first.

```python
import threading
from confish import Confish, Action, SkipAction

client = Confish(env_id="...", api_key="...")
stop = threading.Event()

def handler(action: Action, ctx) -> dict | None:
    if action.type == "place_order":
        ctx.update("Submitting order", {"params": action.params})
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
client.actions.update("action_id", "progress", {"step": 2})
client.actions.complete("action_id", {"order_id": "abc"})
client.actions.fail("action_id", {"error": "timeout"})
```

## Webhook verification

```python
from flask import Flask, request, abort
from confish.webhook import verify
import os

app = Flask(__name__)

@app.post("/webhook")
def webhook():
    if not verify(
        body=request.data,
        signature=request.headers.get("X-Confish-Signature"),
        secret=os.environ["CONFISH_WEBHOOK_SECRET"],
    ):
        abort(401, "invalid signature")
    payload = request.get_json()
    # handle payload['event'] ...
    return "", 200
```

`verify` uses constant-time comparison and rejects timestamps older than 5 minutes by default. Pass `tolerance_seconds=0` to disable timestamp checking. Always pass the **raw, unparsed body** — re-serializing parsed JSON breaks verification.

## Errors

```python
from confish import (
    AuthError,
    ConfishError,
    ConflictError,
    ForbiddenError,
    NetworkError,
    RateLimitError,
    ServerError,
    ValidationError,
)

try:
    client.fetch()
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
    config = client.fetch()
```

## License

MIT
