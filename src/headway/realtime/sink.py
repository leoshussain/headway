from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from google.transit.gtfs_realtime_pb2 import FeedHeader

from headway.realtime.models import FeedInfo


class FileSink:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir

    @staticmethod
    def make_path(
        root_dir: Path,
        feed_info: FeedInfo,
        artifact_ts: float,
        fetch_ts: float,
        suffix: str = ".pb",
    ) -> Path:
        path: Path = (
            root_dir
            / "realtime"
            / "raw"
            / feed_info.provider
            / feed_info.name
            / f"{fetch_ts}_{artifact_ts}{suffix}"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def write(self, feed_info: FeedInfo, header: FeedHeader, payload: bytes) -> Path:
        fetch_ts = datetime.now(tz=UTC).timestamp()
        artifact_ts = header.timestamp
        feed_path = self.make_path(self.root_dir, feed_info, artifact_ts, fetch_ts)

        with TemporaryDirectory(dir=feed_path.parent, prefix=".snapshot-") as temp_dir:
            temp_path = Path(temp_dir) / "payload.tmp"
            with temp_path.open("wb") as f:
                f.write(payload)
            temp_path.replace(feed_path)

        return feed_path
