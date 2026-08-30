from pathlib import Path
from typing import Self

import pytest
from google.transit.gtfs_realtime_pb2 import FeedHeader, FeedMessage

from headway.realtime.models import FeedInfo
from headway.realtime.sink import FileSink


def test_write_preserves_payload_and_path_provenance(
    tmp_path: Path,
    feed_info: FeedInfo,
    feed_message: FeedMessage,
    protobuf_payload: bytes,
) -> None:
    path = FileSink(tmp_path).write(feed_info, feed_message.header, protobuf_payload)

    assert path.read_bytes() == protobuf_payload
    assert path.suffix == ".pb"
    assert path.is_relative_to(
        tmp_path / "realtime" / "raw" / feed_info.provider / feed_info.name
    )
    assert str(feed_message.header.timestamp) in path.name


def test_repeated_header_timestamp_creates_distinct_snapshots(
    tmp_path: Path,
    feed_info: FeedInfo,
    feed_message: FeedMessage,
) -> None:
    sink = FileSink(tmp_path)

    first = sink.write(feed_info, feed_message.header, b"first")
    second = sink.write(feed_info, feed_message.header, b"second")

    assert first != second
    assert first.read_bytes() == b"first"
    assert second.read_bytes() == b"second"


def test_missing_header_timestamp_creates_distinct_nonzero_snapshots(
    tmp_path: Path,
    feed_info: FeedInfo,
) -> None:
    sink = FileSink(tmp_path)
    header = FeedHeader(gtfs_realtime_version="2.0")

    first = sink.write(feed_info, header, b"first")
    second = sink.write(feed_info, header, b"second")

    assert first != second
    assert first.name != "0.pb"
    assert second.name != "0.pb"


def test_existing_snapshot_is_never_overwritten(
    tmp_path: Path,
    feed_info: FeedInfo,
    feed_message: FeedMessage,
) -> None:
    sink = FileSink(tmp_path)
    first = sink.write(feed_info, feed_message.header, b"original")

    sink.write(feed_info, feed_message.header, b"new")

    assert first.read_bytes() == b"original"


def test_failed_write_leaves_no_complete_looking_snapshot(
    tmp_path: Path,
    feed_info: FeedInfo,
    feed_message: FeedMessage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_open = Path.open

    class FailingFile:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def write(self, _payload: bytes) -> None:
            raise OSError("disk full")

    def failing_open(
        path: Path, mode: str = "r", *args: object, **kwargs: object
    ) -> object:
        if "w" in mode:
            return FailingFile()
        return original_open(path, mode)

    monkeypatch.setattr(Path, "open", failing_open)

    with pytest.raises(OSError, match="disk full"):
        FileSink(tmp_path).write(feed_info, feed_message.header, b"payload")

    assert not list(tmp_path.rglob("*.pb"))
