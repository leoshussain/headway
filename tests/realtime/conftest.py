from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from google.transit.gtfs_realtime_pb2 import FeedMessage
from pydantic import SecretStr

from headway.realtime.config import RealtimeConfig
from headway.realtime.models import FeedInfo

type ConfigFactory = Callable[..., RealtimeConfig]


@pytest.fixture
def feed_info() -> FeedInfo:
    return FeedInfo(
        name="vehicle_positions",
        provider="test-provider",
        url="https://example.test/vehicle-positions",
        poll_interval_seconds=30.0,
        api_key=SecretStr("test-secret"),
    )


@pytest.fixture
def protobuf_payload() -> bytes:
    return (Path(__file__).parent / "fixtures" / "feed_message.pb").read_bytes()


@pytest.fixture
def feed_message(protobuf_payload: bytes) -> FeedMessage:
    message = FeedMessage()
    message.ParseFromString(protobuf_payload)
    return message


@pytest.fixture
def config_factory(tmp_path: Path) -> ConfigFactory:
    from headway.realtime.config import RealtimeConfig

    def make_config(**overrides: Any) -> RealtimeConfig:
        values: dict[str, Any] = {
            "data_dir": tmp_path,
            "providers": {"test-provider": {"api_key": "test-secret"}},
            "feeds": {
                "vehicle_positions": {
                    "provider": "test-provider",
                    "url": "https://example.test/vehicle-positions",
                    "poll_interval_seconds": 30,
                }
            },
        }
        values.update(overrides)
        return RealtimeConfig(**values)

    return make_config
