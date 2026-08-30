import asyncio
import logging
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from google.protobuf.message import DecodeError

from headway.realtime.collector import RealtimeCollector
from headway.realtime.models import FeedInfo
from headway.realtime.sink import FileSink


def test_decode_valid_fixture(protobuf_payload: bytes) -> None:
    message = RealtimeCollector.decode(protobuf_payload)

    assert message.header.gtfs_realtime_version == "2.0"
    assert message.header.timestamp == 1_700_000_000
    assert [entity.id for entity in message.entity] == ["vehicle-1"]
    assert message.entity[0].vehicle.vehicle.id == "bus-42"


def test_decode_rejects_malformed_payload() -> None:
    with pytest.raises(DecodeError):
        RealtimeCollector.decode(b"not a protobuf")


@pytest.mark.asyncio
async def test_collect_once_fetches_and_preserves_exact_payload(
    tmp_path: Path,
    feed_info: FeedInfo,
    protobuf_payload: bytes,
) -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=protobuf_payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        path = await RealtimeCollector(client, FileSink(tmp_path)).collect_once(
            feed_info
        )

    assert [str(request.url) for request in requests] == [feed_info.url]
    assert path.read_bytes() == protobuf_payload


@pytest.mark.asyncio
async def test_collect_once_propagates_http_failure(
    tmp_path: Path,
    feed_info: FeedInfo,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        collector = RealtimeCollector(client, FileSink(tmp_path))
        with pytest.raises(httpx.HTTPStatusError):
            await collector.collect_once(feed_info)

    assert not list(tmp_path.rglob("*.pb"))


@pytest.mark.asyncio
async def test_collect_once_propagates_decode_failure(
    tmp_path: Path,
    feed_info: FeedInfo,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not a protobuf", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        collector = RealtimeCollector(client, FileSink(tmp_path))
        with pytest.raises(DecodeError):
            await collector.collect_once(feed_info)

    assert not list(tmp_path.rglob("*.pb"))


@pytest.mark.asyncio
async def test_poll_feed_retries_expected_failure_without_real_sleep(
    monkeypatch: pytest.MonkeyPatch,
    feed_info: FeedInfo,
) -> None:
    collector = RealtimeCollector(Mock(), Mock())
    attempts = 0

    async def collect_once(_feed_info: FeedInfo) -> Path:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("offline")
        raise asyncio.CancelledError

    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(collector, "collect_once", collect_once)
    monkeypatch.setattr(asyncio, "sleep", sleep)

    with pytest.raises(asyncio.CancelledError):
        await collector.poll_feed(feed_info)

    assert attempts == 2
    assert len(delays) == 1
    assert 0 < delays[0] <= feed_info.poll_interval_seconds


@pytest.mark.asyncio
async def test_poll_feed_cancellation_does_not_start_another_poll(
    monkeypatch: pytest.MonkeyPatch,
    feed_info: FeedInfo,
) -> None:
    collector = RealtimeCollector(Mock(), Mock())
    attempts = 0

    async def collect_once(_feed_info: FeedInfo) -> Path:
        nonlocal attempts
        attempts += 1
        raise asyncio.CancelledError

    sleep = Mock()
    monkeypatch.setattr(collector, "collect_once", collect_once)
    monkeypatch.setattr(asyncio, "sleep", sleep)

    with pytest.raises(asyncio.CancelledError):
        await collector.poll_feed(feed_info)

    assert attempts == 1
    sleep.assert_not_called()


@pytest.mark.asyncio
async def test_success_log_contains_operational_context_without_secrets(
    tmp_path: Path,
    feed_info: FeedInfo,
    protobuf_payload: bytes,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=protobuf_payload, request=request)

    caplog.set_level(logging.INFO)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        path = await RealtimeCollector(client, FileSink(tmp_path)).collect_once(
            feed_info
        )

    log_text = caplog.text
    assert feed_info.provider in log_text
    assert feed_info.name in log_text
    assert "success" in log_text
    assert str(len(protobuf_payload)) in log_text
    assert "entities=1" in log_text
    assert str(path) in log_text
    assert "latency" in log_text
    assert feed_info.api_key.get_secret_value() not in log_text
    assert protobuf_payload.hex() not in log_text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "category"),
    [
        (httpx.ConnectError("offline"), "http"),
        (DecodeError("invalid"), "decode"),
        (OSError("disk full"), "storage"),
    ],
)
async def test_failure_log_identifies_feed_and_error_category(
    monkeypatch: pytest.MonkeyPatch,
    feed_info: FeedInfo,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    category: str,
) -> None:
    collector = RealtimeCollector(Mock(), Mock())

    async def collect_once(_feed_info: FeedInfo) -> Path:
        raise error

    async def stop_after_failure(_delay: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(collector, "collect_once", collect_once)
    monkeypatch.setattr(asyncio, "sleep", stop_after_failure)
    caplog.set_level(logging.ERROR)

    with pytest.raises(asyncio.CancelledError):
        await collector.poll_feed(feed_info)

    assert feed_info.provider in caplog.text
    assert feed_info.name in caplog.text
    assert category in caplog.text.lower()
    assert feed_info.api_key.get_secret_value() not in caplog.text
