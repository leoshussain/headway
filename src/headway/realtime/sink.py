from pathlib import Path

from google.transit.gtfs_realtime_pb2 import FeedHeader

from headway.realtime.models import FeedInfo


class FileSink:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir

    @staticmethod
    def make_path(
        root_dir: Path,
        feed_info: FeedInfo,
        header: FeedHeader,
        suffix: str = ".pb",
    ) -> Path:
        path: Path = (
            root_dir
            / "realtime"
            / "raw"
            / feed_info.provider
            / feed_info.name
            / str(header.timestamp)
        )
        path = path.with_suffix(suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def write(self, feed_info: FeedInfo, header: FeedHeader, payload: bytes) -> Path:
        feed_path = self.make_path(self.root_dir, feed_info, header)

        with feed_path.open("wb") as f:
            f.write(payload)

        return feed_path
