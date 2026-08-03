from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ysa_worker.chat_replay import (
    ChatReplayAuthenticationError,
    ChatReplayGateway,
    ChatReplayNotReady,
    ChatReplayProtocolError,
    ChatReplayTemporaryError,
    ChatReplayUnavailable,
)

ReadinessState = Literal["pending", "ready"]


class ArchiveReadinessError(RuntimeError):
    code = "ARCHIVE_READINESS_FAILED"
    retryable = False


class ArchiveReadinessTemporaryError(ArchiveReadinessError):
    code = "ARCHIVE_READINESS_TEMPORARILY_UNAVAILABLE"
    retryable = True


class ArchiveUnavailable(ArchiveReadinessError):
    code = "ARCHIVE_UNAVAILABLE"


class ChatReplayPermanentlyUnavailable(ArchiveReadinessError):
    code = "CHAT_REPLAY_UNAVAILABLE"


class ArchiveReadinessTimedOut(ArchiveReadinessError):
    code = "ARCHIVE_READINESS_TIMEOUT"


@dataclass(frozen=True)
class ReadinessResult:
    state: ReadinessState
    archive_ready: bool
    chat_replay_ready: bool
    next_check_at: datetime
    reason_code: str


class ArchiveReadinessGateway:
    def __init__(
        self,
        api_key: str,
        youtube_base_url: str,
        chat_replay_base_url: str,
        timeout_seconds: float = 10,
        gateway_bearer_token: str = "",
    ) -> None:
        if not api_key.strip():
            raise ValueError("YSA_YOUTUBE_API_KEY is required")
        self.api_key = api_key
        self.youtube_base_url = youtube_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        token = gateway_bearer_token or os.environ.get(
            "YSA_GATEWAY_BEARER_TOKEN", ""
        ).strip()
        self.chat_gateway = ChatReplayGateway(
            chat_replay_base_url,
            token,
            timeout_seconds,
        )

    def check(
        self,
        video_id: str,
        stream_started_at: datetime,
        stream_ended_at: datetime,
        now: datetime | None = None,
    ) -> ReadinessResult:
        current = now or datetime.now(UTC)
        waited = current - stream_ended_at.astimezone(UTC)
        if waited > timedelta(hours=24):
            raise ArchiveReadinessTimedOut(
                "archive or chat replay was not ready within 24 hours"
            )

        archive_ready = self._archive_ready(video_id)
        chat_ready = self._chat_replay_ready(
            video_id,
            stream_started_at,
            allow_missing=waited <= timedelta(hours=24),
        )
        if archive_ready and chat_ready:
            return ReadinessResult(
                "ready",
                True,
                True,
                current,
                "archive_and_chat_ready",
            )

        delay = _pending_delay(waited)
        reason = "archive_processing" if not archive_ready else "chat_replay_processing"
        return ReadinessResult(
            "pending",
            archive_ready,
            chat_ready,
            current + delay,
            reason,
        )

    def _archive_ready(self, video_id: str) -> bool:
        query = urlencode(
            {
                "part": "status,contentDetails,liveStreamingDetails",
                "id": video_id,
                "key": self.api_key,
            }
        )
        request = Request(
            f"{self.youtube_base_url}/videos?{query}",
            headers={"Accept": "application/json", "User-Agent": "ysa-worker/0.1"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.load(response)
        except HTTPError as error:
            if error.code in {401, 403, 404, 410}:
                raise ArchiveUnavailable("archive cannot be accessed") from error
            if error.code == 429 or error.code >= 500:
                raise ArchiveReadinessTemporaryError(
                    "YouTube archive status is temporarily unavailable"
                ) from error
            raise ArchiveReadinessError("unexpected YouTube archive response") from error
        except (TimeoutError, URLError, json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ArchiveReadinessTemporaryError(
                "YouTube archive status request failed"
            ) from error

        item = _first_item(payload)
        status = item.get("status")
        details = item.get("contentDetails")
        if not isinstance(status, dict) or not isinstance(details, dict):
            raise ArchiveReadinessTemporaryError("archive status response is incomplete")
        upload_status = status.get("uploadStatus")
        if upload_status in {"failed", "rejected", "deleted"}:
            raise ArchiveUnavailable(f"archive upload status is {upload_status}")
        duration = details.get("duration")
        return upload_status == "processed" and isinstance(duration, str) and bool(duration)

    def _chat_replay_ready(
        self,
        video_id: str,
        stream_started_at: datetime,
        allow_missing: bool,
    ) -> bool:
        try:
            self.chat_gateway.fetch_page(video_id, stream_started_at)
            return True
        except ChatReplayNotReady:
            return False
        except ChatReplayUnavailable as error:
            if allow_missing:
                return False
            raise ChatReplayPermanentlyUnavailable(
                "chat replay is permanently unavailable"
            ) from error
        except ChatReplayTemporaryError as error:
            raise ArchiveReadinessTemporaryError(
                "chat replay readiness check failed"
            ) from error
        except (ChatReplayProtocolError, ChatReplayAuthenticationError) as error:
            raise ArchiveReadinessError("chat replay Gateway failed") from error


def _first_item(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ArchiveReadinessTemporaryError("archive status root must be an object")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ArchiveUnavailable("archive video was not found")
    item = items[0]
    if not isinstance(item, dict):
        raise ArchiveReadinessTemporaryError("archive item is invalid")
    return item


def _pending_delay(waited: timedelta) -> timedelta:
    if waited < timedelta(hours=1):
        return timedelta(minutes=2)
    if waited < timedelta(hours=6):
        return timedelta(minutes=5)
    return timedelta(minutes=15)
