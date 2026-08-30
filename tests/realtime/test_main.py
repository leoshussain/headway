import asyncio
from collections.abc import Callable
from unittest.mock import Mock

import pytest

from headway.realtime import __main__ as entrypoint
from headway.realtime.config import RealtimeConfig
from headway.realtime.models import FeedInfo


@pytest.mark.asyncio
async def test_run_rejects_empty_feed_selection(
    config_factory: Callable[..., RealtimeConfig],
) -> None:
    config = config_factory()

    with pytest.raises(ValueError, match="feed"):
        await entrypoint.run(config, [])


@pytest.mark.asyncio
async def test_run_rejects_mixed_provider_authentication_before_polling(
    config_factory: Callable[..., RealtimeConfig],
) -> None:
    providers = {
        "provider-a": {"api_key": "secret-a"},
        "provider-b": {"api_key": "secret-b"},
    }
    feeds = {
        "feed-a": {
            "provider": "provider-a",
            "url": "https://a.example.test/feed",
            "poll_interval_seconds": 30,
        },
        "feed-b": {
            "provider": "provider-b",
            "url": "https://b.example.test/feed",
            "poll_interval_seconds": 30,
        },
    }
    config = config_factory(providers=providers, feeds=feeds)

    with pytest.raises(ValueError, match="provider|authentication"):
        async with asyncio.timeout(0.1):
            await entrypoint.run(config, ["feed-a", "feed-b"])


@pytest.mark.asyncio
async def test_run_resolves_all_feeds_before_starting_http_client(
    monkeypatch: pytest.MonkeyPatch,
    config_factory: Callable[..., RealtimeConfig],
) -> None:
    config = config_factory()
    client = Mock()
    monkeypatch.setattr(entrypoint.httpx, "AsyncClient", client)

    with pytest.raises(ValueError, match="missing"):
        await entrypoint.run(config, ["vehicle_positions", "missing"])

    client.assert_not_called()


@pytest.mark.asyncio
async def test_independent_feed_task_survives_another_task_failure(
    monkeypatch: pytest.MonkeyPatch,
    config_factory: Callable[..., RealtimeConfig],
) -> None:
    feeds = {
        "failing": {
            "provider": "test-provider",
            "url": "https://example.test/failing",
            "poll_interval_seconds": 30,
        },
        "healthy": {
            "provider": "test-provider",
            "url": "https://example.test/healthy",
            "poll_interval_seconds": 30,
        },
    }
    config = config_factory(feeds=feeds)
    healthy_completed = asyncio.Event()

    async def poll_feed(_self: object, feed_info: FeedInfo) -> None:
        if feed_info.name == "failing":
            await asyncio.sleep(0)
            raise RuntimeError("unexpected failure")
        await asyncio.sleep(0)
        healthy_completed.set()

    monkeypatch.setattr(entrypoint.RealtimeCollector, "poll_feed", poll_feed)

    with pytest.raises(ExceptionGroup):
        await entrypoint.run(config, ["failing", "healthy"])

    assert healthy_completed.is_set()
