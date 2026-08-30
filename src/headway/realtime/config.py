from importlib.resources import files
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from headway.realtime.models import FeedInfo

DEFAULT_CONFIG = files("headway.realtime.resources").joinpath("defaults.yaml")


class ProviderConfig(BaseModel):
    api_key: SecretStr

    model_config = ConfigDict(frozen=True)


class FeedConfig(BaseModel):
    provider: str
    url: str
    poll_interval_seconds: float = Field(gt=0.0)

    model_config = ConfigDict(frozen=True)


class RealtimeConfig(BaseSettings):
    data_dir: Path
    providers: dict[str, ProviderConfig]
    feeds: dict[str, FeedConfig]

    model_config = SettingsConfigDict(
        frozen=True,
        env_file=".env",
        env_nested_delimiter="__",
    )

    def get_feed(self, name: str) -> FeedInfo:
        feed = self.feeds.get(name)
        if feed is None:
            raise ValueError(
                f"Feed {name!r} does not exist. Must be one of {list(self.feeds.keys())}"
            )

        provider = self.providers.get(feed.provider)
        if provider is None:
            raise ValueError(
                f"Provider {feed.provider!r} does not exist. Must be one of {list(self.providers.keys())}"
            )

        return FeedInfo(
            name=name,
            provider=feed.provider,
            url=feed.url,
            poll_interval_seconds=feed.poll_interval_seconds,
            api_key=provider.api_key,
        )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls, yaml_file=DEFAULT_CONFIG),
            file_secret_settings,
        )

    @model_validator(mode="after")
    def validate_feed_providers(self) -> "RealtimeConfig":
        for name, feed in self.feeds.items():
            if feed.provider not in self.providers:
                raise ValueError(
                    f"Feed {name!r} references unknown provider {feed.provider!r}"
                )
        return self
