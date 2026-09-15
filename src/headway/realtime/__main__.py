"""Entrypoint for GTFS-RT collection."""

import asyncio
import logging

import httpx

from headway.realtime.collector import RealtimeCollector
from headway.realtime.config import RealtimeConfig
from headway.realtime.models import FeedInfo
from headway.realtime.sink import FileSink

logger = logging.getLogger(__name__)


async def run(config: RealtimeConfig, target_feed_names: list[str]) -> None:
    if not target_feed_names:
        raise ValueError("target_feed_names must not be empty.")

    sink = FileSink(config.data_dir)
    feed_infos: list[FeedInfo] = [
        config.get_feed(feed_name) for feed_name in target_feed_names
    ]

    async with httpx.AsyncClient(timeout=10.0) as client:
        collector = RealtimeCollector(client, sink)

        async with asyncio.TaskGroup() as group:
            for feed_info in feed_infos:
                group.create_task(
                    collector.poll_feed(
                        feed_info,
                        headers={"apiKey": feed_info.api_key.get_secret_value()},
                    ),
                    name=f"poll-{feed_info.name}",
                )


async def main() -> int:
    try:
        config = RealtimeConfig()
        await run(config, ["stm_trip_updates", "stm_vehicle_positions"])
        print("Successfully collected.")
    except Exception:
        logger.exception("GTFS-RT collection failed")
        return 1

    return 0


def cli() -> None:
    """Run GTFS-RT collection."""
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(asyncio.run(main()))


if __name__ == "__main__":
    cli()
