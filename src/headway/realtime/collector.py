import asyncio
import logging
from collections.abc import Mapping
from pathlib import Path

import httpx
from google.protobuf.message import DecodeError
from google.transit.gtfs_realtime_pb2 import FeedMessage
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from headway.realtime.models import FeedInfo
from headway.realtime.sink import FileSink

logger = logging.getLogger(__name__)

RETRYABLE_STATUSES = {408, 425, 429, 500, 502, 503, 504}


def is_retryable_fetch_error(error: BaseException) -> bool:
    return isinstance(
        error,
        (
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
            httpx.ProxyError,
        ),
    ) or (
        isinstance(error, httpx.HTTPStatusError)
        and error.response.status_code in RETRYABLE_STATUSES
    )


def log_fetch_retry(state: RetryCallState) -> None:
    outcome = state.outcome
    next_action = state.next_action
    if outcome and next_action:
        error = outcome.exception()
        logger.warning(
            "Retrying fetch (attempt=%d delay_seconds=%.2f, error=%s)",
            state.attempt_number,
            next_action.sleep,
            type(error).__name__,
        )


class RealtimeCollector:
    def __init__(self, client: httpx.AsyncClient, sink: FileSink):
        self.client = client
        self.sink = sink

    @staticmethod
    @retry(
        retry=retry_if_exception(is_retryable_fetch_error),
        stop=stop_after_attempt(3),
        wait=wait_random_exponential(multiplier=0.5, max=5),
        before_sleep=log_fetch_retry,
        reraise=True,
    )
    async def _fetch(
        client: httpx.AsyncClient,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response

    @staticmethod
    def decode(payload: bytes) -> FeedMessage:
        message: FeedMessage = FeedMessage()
        message.ParseFromString(payload)

        if not message.IsInitialized():
            missing = ",".join(message.FindInitializationErrors())
            raise DecodeError(f"Missing required portobuf fields: {missing}")

        return message

    async def collect_once(
        self,
        feed_info: FeedInfo,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> Path:
        start_time = asyncio.get_running_loop().time()

        response = await self._fetch(
            self.client,
            feed_info.url,
            headers=headers,
        )
        message = self.decode(response.content)
        path = self.sink.write(
            feed_info=feed_info,
            header=message.header,
            payload=response.content,
        )

        latency = asyncio.get_running_loop().time() - start_time
        logger.info(
            "Collection successful (provider=%s feed=%s bytes=%d entities=%d path=%s latency_ms=%.1f)",
            feed_info.provider,
            feed_info.name,
            len(response.content),
            len(message.entity),
            path,
            latency * 1000,
        )
        return path

    @staticmethod
    def _log_collection_failure(feed_info: FeedInfo, *, category: str) -> None:
        logger.exception(
            "Collection failed (provider=%s feed=%s category=%s)",
            feed_info.provider,
            feed_info.name,
            category,
        )

    async def poll_feed(
        self,
        feed_info: FeedInfo,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        while True:
            start_time = asyncio.get_running_loop().time()
            try:
                await self.collect_once(feed_info, headers=headers)
            except httpx.HTTPError:
                self._log_collection_failure(feed_info, category="http")
            except DecodeError:
                self._log_collection_failure(feed_info, category="decode")
            except OSError:
                self._log_collection_failure(feed_info, category="storage")

            elapsed = asyncio.get_running_loop().time() - start_time
            delay = max(0.0, feed_info.poll_interval_seconds - elapsed)
            await asyncio.sleep(delay)
