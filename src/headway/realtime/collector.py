import asyncio
import logging
from pathlib import Path

import httpx
from google.protobuf.message import DecodeError
from google.transit.gtfs_realtime_pb2 import FeedMessage

from headway.realtime.models import FeedInfo
from headway.realtime.sink import FileSink

logger = logging.getLogger(__name__)

class RealtimeCollector:
    def __init__(self, client: httpx.AsyncClient, sink: FileSink):
        self.client = client
        self.sink = sink

    @staticmethod
    async def _fetch(client: httpx.AsyncClient, url: str) -> httpx.Response:
        response = await client.get(url)
        response.raise_for_status()
        return response

    @staticmethod
    def decode(payload: bytes) -> FeedMessage:
        message: FeedMessage = FeedMessage()
        message.ParseFromString(payload)
        return message

    async def collect_once(self, feed_info: FeedInfo) -> Path:
        response = await self._fetch(self.client, feed_info.url)
        message = self.decode(response.content)

        return self.sink.write(feed_info=feed_info, header=message.header, payload=response.content)

    async def poll_feed(self, feed_info: FeedInfo) -> None:
        while True:
            start_time = asyncio.get_running_loop().time()
            try:
                await self.collect_once(feed_info)
            except (httpx.HTTPError, DecodeError, OSError):
                logger.exception("Failed to collect %s", feed_info.name)

            elapsed = asyncio.get_running_loop().time() - start_time
            delay = max(0.0, feed_info.poll_interval_seconds - elapsed)
            await asyncio.sleep(delay)
