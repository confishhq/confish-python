# Changelog

## 0.2.0 (2026-07-09)

Coordinated minor release across all five confish SDKs. Breaking changes are
free in this release — the surface is treated as informally frozen afterwards.

### Added

- **Feeds.** `client.feed(slug)` returns a bound `Feed` handle (no HTTP on
  construction) with `set(external_id, data, ttl=None)`, `replace(items)`,
  `list()`, and `delete(external_id)`. `set` upserts with declarative PUT
  semantics — omitting `ttl` makes the item permanent and clears any existing
  TTL. `replace` swaps the environment's whole partition in one all-or-nothing
  request (absent items are deleted; an empty list clears the feed) and
  returns a `FeedReplaceResult` with `created`/`updated`/`deleted` counts.
  New `FeedItem` dataclass.
- `NotFoundError` in the shared error hierarchy — 404s previously fell
  through to the base `ConfishError`.
- `emergency` log level (full RFC 5424 set) via `client.logs.emergency(...)`
  and the `LogLevel` type.

### Breaking

- **Config namespace.** `client.fetch()` / `client.update()` /
  `client.replace()` moved to `client.config.fetch()` /
  `client.config.update()` / `client.config.replace()`. The root methods are
  removed. Signatures and wire calls are unchanged.
- **Logs consolidation.** `client.logger` renamed to `client.logs`; the flat
  `client.log(...)` is removed in favor of
  `client.logs.write(level, message, context=None)`. Per-level methods remain.
  The `Logger` class is replaced by `Logs`.
- **Webhook verify.** `confish.webhook.verify(...)` now returns the parsed
  `WebhookPayload` on success (was `True`) and raises on failure (was
  `False`): `WebhookSignatureError` for a missing/malformed/mismatched
  signature, `WebhookTimestampError` for a timestamp outside the tolerance
  window. Parsing and verification are one operation.
- **`actions.update` renamed to `actions.progress`.** Same wire call. The
  consumer handler context method is renamed too: `ctx.progress(...)`.
