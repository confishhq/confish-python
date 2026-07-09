"""Feeds API."""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ._http import HttpClient
from ._types import FeedItem, FeedReplaceResult


class Feed:
    """A handle bound to one feed slug via :meth:`Confish.feed`.

    Constructing the handle performs no HTTP; requests happen when a method
    is called. An unknown slug raises :class:`~confish.NotFoundError` from
    every method.
    """

    def __init__(self, http: HttpClient, env_id: str, slug: str) -> None:
        self._http = http
        self._env_id = env_id
        self._slug = slug

    def set(
        self,
        external_id: str,
        data: dict[str, Any],
        *,
        ttl: int | None = None,
    ) -> FeedItem:
        """Create or replace (upsert) an item by its client-supplied external ID.

        PUT semantics are declarative full-replace: the item's data becomes
        exactly ``data``, and the TTL becomes exactly ``ttl``. Passing
        ``ttl=None`` (the default) makes the item permanent — it **clears**
        any TTL set by a previous ``set``. ``ttl`` is in seconds (1 to
        2,592,000 — 30 days).
        """
        body: dict[str, Any] = {"data": data}
        if ttl is not None:
            body["ttl"] = ttl
        response = self._http.request(
            "PUT",
            f"/c/{self._env_id}/feeds/{self._slug}/items/{quote(external_id, safe='')}",
            body=body,
        )
        return FeedItem.from_dict(response)

    def replace(self, items: list[dict[str, Any]]) -> FeedReplaceResult:
        """Replace the environment's entire partition with exactly ``items``.

        Built for sync-style cron jobs pushing their full dataset in one
        request. Each item is a dict with ``external_id``, ``data``, and an
        optional ``ttl`` (seconds; omitted or ``None`` means permanent, same
        as :meth:`set`). Existing IDs update in place, new IDs are created,
        and **anything absent from ``items`` is deleted** — an empty list
        clears the feed.

        All-or-nothing: duplicate external IDs, payloads over the plan's item
        cap, or any schema-invalid item raise
        :class:`~confish.ValidationError` (errors keyed ``items.{i}.data...``)
        with nothing written.
        """
        body_items: list[dict[str, Any]] = []
        for item in items:
            body_item: dict[str, Any] = {
                "external_id": item["external_id"],
                "data": item["data"],
            }
            if item.get("ttl") is not None:
                body_item["ttl"] = item["ttl"]
            body_items.append(body_item)
        response = self._http.request(
            "PUT",
            f"/c/{self._env_id}/feeds/{self._slug}/items",
            body={"items": body_items},
        )
        return FeedReplaceResult.from_dict(response)

    def list(self) -> list[FeedItem]:
        """Return the environment's live items, newest first."""
        response = self._http.request(
            "GET", f"/c/{self._env_id}/feeds/{self._slug}/items"
        )
        return [FeedItem.from_dict(item) for item in response.get("items", [])]

    def delete(self, external_id: str) -> None:
        """Delete an item by external ID. Idempotent — deleting a missing item succeeds."""
        self._http.request(
            "DELETE", f"/c/{self._env_id}/feeds/{self._slug}/items/{quote(external_id, safe='')}"
        )
