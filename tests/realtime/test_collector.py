import asyncio
import logging
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from google.protobuf.message import DecodeError
from google.transit.gtfs_realtime_pb2 import FeedMessage

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


@pytest.mark.parametrize(
    ("message", "missing_field"),
    [
        pytest.param(FeedMessage(), "header", id="missing-header"),
        pytest.param(
            FeedMessage(header={}),
            "header.gtfs_realtime_version",
            id="missing-version",
        ),
        pytest.param(
            FeedMessage(header={"gtfs_realtime_version": "2.0"}, entity=[{}]),
            "entity[0].id",
            id="missing-entity-id",
        ),
    ],
)
def test_decode_rejects_missing_required_fields(
    message: FeedMessage, missing_field: str
) -> None:
    # Partial serialization deliberately creates parseable, incomplete protobufs.
    payload = message.SerializePartialToString()

    with pytest.raises(DecodeError) as exc_info:
        RealtimeCollector.decode(payload)

    assert missing_field in str(exc_info.value)


def test_decode_accepts_complete_header_without_entities() -> None:
    original = FeedMessage(
        header={"gtfs_realtime_version": "2.0", "timestamp": 1_700_000_000}
    )

    message = RealtimeCollector.decode(original.SerializeToString())

    assert message == original
    assert len(message.entity) == 0


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
            feed_info,
            headers={"apiKey": "test-key"},
        )

    assert [str(request.url) for request in requests] == [feed_info.url]
    assert requests[0].headers["apiKey"] == "test-key"
    assert path.read_bytes() == protobuf_payload


@pytest.mark.asyncio
async def test_collect_once_propagates_http_failure(
    tmp_path: Path,
    feed_info: FeedInfo,
) -> None:
    requests = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(503, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        collector = RealtimeCollector(client, FileSink(tmp_path))
        with pytest.raises(httpx.HTTPStatusError):
            await collector.collect_once(feed_info)

    assert requests == 3
    assert not list(tmp_path.rglob("*.pb"))


@pytest.mark.asyncio
async def test_collect_once_does_not_retry_non_retryable_http_failure(
    tmp_path: Path,
    feed_info: FeedInfo,
) -> None:
    requests = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(401, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        collector = RealtimeCollector(client, FileSink(tmp_path))
        with pytest.raises(httpx.HTTPStatusError):
            await collector.collect_once(feed_info)

    assert requests == 1
    assert not list(tmp_path.rglob("*.pb"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "payload"),
    [
        pytest.param(200, b"not a protobuf", id="malformed"),
        pytest.param(200, b"", id="empty-200"),
        pytest.param(204, b"", id="empty-204"),
        pytest.param(
            200,
            FeedMessage(header={}).SerializePartialToString(),
            id="missing-version",
        ),
    ],
)
async def test_collect_once_propagates_decode_failure(
    tmp_path: Path,
    feed_info: FeedInfo,
    status_code: int,
    payload: bytes,
    caplog: pytest.LogCaptureFixture,
) -> None:
    requests = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(status_code, content=payload, request=request)

    caplog.set_level(logging.INFO, logger="headway.realtime.collector")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        collector = RealtimeCollector(client, FileSink(tmp_path))
        with pytest.raises(DecodeError):
            await collector.collect_once(feed_info)

    assert requests == 1
    assert not list(tmp_path.rglob("*.pb"))
    assert "Collection successful" not in caplog.text


@pytest.mark.asyncio
async def test_poll_feed_continues_after_expected_failure_without_real_sleep(
    monkeypatch: pytest.MonkeyPatch,
    feed_info: FeedInfo,
) -> None:
    collector = RealtimeCollector(Mock(), Mock())
    attempts = 0

    async def collect_once(_feed_info: FeedInfo, **_kwargs: object) -> Path:
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

    async def collect_once(_feed_info: FeedInfo, **_kwargs: object) -> Path:
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
async def test_poll_feed_propagates_unexpected_failure(
    monkeypatch: pytest.MonkeyPatch,
    feed_info: FeedInfo,
) -> None:
    collector = RealtimeCollector(Mock(), Mock())

    async def collect_once(_feed_info: FeedInfo, **_kwargs: object) -> Path:
        raise RuntimeError("programming defect")

    sleep = Mock()
    monkeypatch.setattr(collector, "collect_once", collect_once)
    monkeypatch.setattr(asyncio, "sleep", sleep)

    with pytest.raises(RuntimeError, match="programming defect"):
        await collector.poll_feed(feed_info)

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

    async def collect_once(_feed_info: FeedInfo, **_kwargs: object) -> Path:
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
