from dataclasses import dataclass

from pydantic import SecretStr


@dataclass(frozen=True)
class FeedInfo:
    name: str
    provider: str
    url: str
    poll_interval_seconds: float
    api_key: SecretStr
