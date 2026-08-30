from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from headway.realtime.config import RealtimeConfig


def test_packaged_defaults_are_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROVIDERS__STM__API_KEY", "test-secret")

    config = RealtimeConfig(_env_file=None)

    assert config.data_dir == Path("data")
    assert set(config.feeds) == {"stm_trip_updates", "stm_vehicle_positions"}
    assert config.get_feed("stm_trip_updates").provider == "stm"


def test_constructor_values_override_environment(
    monkeypatch: pytest.MonkeyPatch,
    config_factory: Callable[..., RealtimeConfig],
) -> None:
    monkeypatch.setenv("DATA_DIR", "/from-environment")

    config = config_factory(data_dir=Path("/from-constructor"))

    assert config.data_dir == Path("/from-constructor")


def test_environment_overrides_packaged_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATA_DIR", "/from-environment")
    monkeypatch.setenv("PROVIDERS__STM__API_KEY", "test-secret")

    config = RealtimeConfig(_env_file=None)

    assert config.data_dir == Path("/from-environment")


def test_provider_credentials_are_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROVIDERS__STM__API_KEY", raising=False)

    with pytest.raises(ValidationError, match="providers"):
        RealtimeConfig(_env_file=None)


def test_unknown_feed_provider_is_rejected(
    config_factory: Callable[..., RealtimeConfig],
) -> None:
    feeds = {
        "vehicle_positions": {
            "provider": "missing-provider",
            "url": "https://example.test/vehicle-positions",
            "poll_interval_seconds": 30,
        }
    }

    with pytest.raises(ValidationError, match="unknown provider 'missing-provider'"):
        config_factory(feeds=feeds)


def test_unknown_feed_name_has_actionable_error(
    config_factory: Callable[..., RealtimeConfig],
) -> None:
    config = config_factory()

    with pytest.raises(ValueError, match="does not exist.*vehicle_positions"):
        config.get_feed("missing")


@pytest.mark.parametrize("interval", [0, -1])
def test_poll_interval_must_be_positive(
    interval: int,
    config_factory: Callable[..., RealtimeConfig],
) -> None:
    feeds = {
        "vehicle_positions": {
            "provider": "test-provider",
            "url": "https://example.test/vehicle-positions",
            "poll_interval_seconds": interval,
        }
    }

    with pytest.raises(ValidationError, match="greater than 0"):
        config_factory(feeds=feeds)
