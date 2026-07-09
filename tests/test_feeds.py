from __future__ import annotations

from typing import Any

import pytest

from confish import Confish, FeedItem, FeedReplaceResult, NotFoundError, ValidationError


def _item(external_id: str = "sitemap-crawl") -> dict[str, Any]:
    return {
        "id": "fi_1",
        "external_id": external_id,
        "data": {"status": "running"},
        "expires_at": None,
        "created_at": "2026-07-09T12:00:00+00:00",
        "updated_at": "2026-07-09T12:00:00+00:00",
    }


def test_set_puts_data_with_ttl(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test/feeds/jobs/items/sitemap-crawl",
        method="PUT",
        status_code=201,
        json={**_item(), "expires_at": "2026-07-10T12:00:00+00:00"},
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")
    item = client.feed("jobs").set("sitemap-crawl", {"status": "running"}, ttl=86400)
    assert isinstance(item, FeedItem)
    assert item.external_id == "sitemap-crawl"
    assert item.expires_at == "2026-07-10T12:00:00+00:00"

    import json
    body = json.loads(httpx_mock.get_request().content)
    assert body == {"data": {"status": "running"}, "ttl": 86400}


def test_set_omits_ttl_key_when_unset(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test/feeds/jobs/items/sitemap-crawl",
        method="PUT",
        json=_item(),
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")
    item = client.feed("jobs").set("sitemap-crawl", {"status": "running"})
    assert item.expires_at is None

    import json
    body = json.loads(httpx_mock.get_request().content)
    assert body == {"data": {"status": "running"}}
    assert "ttl" not in body


def test_list_unwraps_items_array(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test/feeds/jobs/items",
        method="GET",
        json={"items": [_item("a"), _item("b")]},
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")
    items = client.feed("jobs").list()
    assert len(items) == 2
    assert items[0].external_id == "a"
    assert isinstance(items[0], FeedItem)
    assert items[0].data == {"status": "running"}


def test_delete_returns_none_on_204(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test/feeds/jobs/items/sitemap-crawl",
        method="DELETE",
        status_code=204,
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")
    assert client.feed("jobs").delete("sitemap-crawl") is None
    assert httpx_mock.get_request().method == "DELETE"


def test_unknown_feed_slug_raises_not_found(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test/feeds/nope/items",
        method="GET",
        status_code=404,
        json={"error": "Feed not found"},
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")
    feed = client.feed("nope")  # constructing the handle performs no HTTP
    with pytest.raises(NotFoundError) as exc:
        feed.list()
    assert exc.value.message == "Feed not found"
    assert exc.value.status_code == 404


def test_schema_mismatch_raises_validation_error(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test/feeds/jobs/items/x",
        method="PUT",
        status_code=422,
        json={
            "message": "invalid",
            "errors": {"data.status": ["The status field is required."]},
        },
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")
    with pytest.raises(ValidationError) as exc:
        client.feed("jobs").set("x", {"wrong": True})
    assert exc.value.errors == {"data.status": ["The status field is required."]}


def test_feed_full_raises_validation_error_with_message_only(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test/feeds/jobs/items/x",
        method="PUT",
        status_code=422,
        json={"error": "Feed is full (100 items). Delete items, set TTLs, or upgrade your plan."},
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")
    with pytest.raises(ValidationError) as exc:
        client.feed("jobs").set("x", {"status": "running"})
    assert exc.value.message.startswith("Feed is full")
    assert exc.value.errors == {}


def test_replace_puts_items_collection_and_parses_counts(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test/feeds/jobs/items",
        method="PUT",
        json={"created": 1, "updated": 2, "deleted": 3},
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")
    result = client.feed("jobs").replace([
        {"external_id": "a", "data": {"status": "running"}, "ttl": 86400},
        {"external_id": "b", "data": {"status": "queued"}},
        {"external_id": "c", "data": {"status": "done"}, "ttl": None},
    ])
    assert isinstance(result, FeedReplaceResult)
    assert (result.created, result.updated, result.deleted) == (1, 2, 3)

    import json
    body = json.loads(httpx_mock.get_request().content)
    assert body == {
        "items": [
            {"external_id": "a", "data": {"status": "running"}, "ttl": 86400},
            {"external_id": "b", "data": {"status": "queued"}},
            {"external_id": "c", "data": {"status": "done"}},
        ]
    }
    assert "ttl" not in body["items"][1]
    assert "ttl" not in body["items"][2]


def test_replace_with_empty_list_clears_feed(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test/feeds/jobs/items",
        method="PUT",
        json={"created": 0, "updated": 0, "deleted": 5},
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")
    result = client.feed("jobs").replace([])
    assert result.deleted == 5

    import json
    body = json.loads(httpx_mock.get_request().content)
    assert body == {"items": []}


def test_replace_is_all_or_nothing_on_invalid_item(httpx_mock):
    httpx_mock.add_response(
        url="https://api.test/c/env_test/feeds/jobs/items",
        method="PUT",
        status_code=422,
        json={
            "message": "invalid",
            "errors": {"items.1.data.status": ["The status field is required."]},
        },
    )
    client = Confish(env_id="env_test", api_key="k", base_url="https://api.test")
    with pytest.raises(ValidationError) as exc:
        client.feed("jobs").replace([
            {"external_id": "a", "data": {"status": "running"}},
            {"external_id": "b", "data": {"wrong": True}},
        ])
    assert exc.value.errors == {"items.1.data.status": ["The status field is required."]}
