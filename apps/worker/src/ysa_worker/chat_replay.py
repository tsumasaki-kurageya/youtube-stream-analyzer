from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ysa_worker.gateway_http import GatewayHTTPError, get_json


class ChatReplayError(RuntimeError):
    code = "CHAT_REPLAY_ERROR"
    retryable = False


class ChatReplayUnavailable(ChatReplayError):
    code = "CHAT_REPLAY_UNAVAILABLE"


class ChatReplayTemporaryError(ChatReplayError):
    code = "CHAT_REPLAY_TEMPORARY_ERROR"
    retryable = True


class ChatReplayNotReady(ChatReplayTemporaryError):
    code = "CHAT_REPLAY_NOT_READY"


class ChatReplayProtocolError(ChatReplayError):
    code = "CHAT_REPLAY_PROTOCOL_CHANGED"


class ChatReplayAuthenticationError(ChatReplayError):
    code = "CHAT_REPLAY_GATEWAY_UNAUTHORIZED"


@dataclass(frozen=True)
class ChatMessage:
    external_id: str
    author_external_id: str | None
    author_name: str
    text: str
    published_at: datetime
    elapsed_milliseconds: int


@dataclass(frozen=True)
class ChatPage:
    messages: tuple[ChatMessage, ...]
    continuation: str | None
    skipped_missing_timestamp: int = 0


class ChatReplayGateway:
    def __init__(
        self,
        base_url: str,
        bearer_token: str,
        timeout_seconds: float = 15,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.bearer_token = bearer_token
        self.timeout_seconds = timeout_seconds

    def fetch_page(
        self,
        video_id: str,
        stream_started_at: datetime,
        continuation: str | None = None,
    ) -> ChatPage:
        query = {"videoId": video_id}
        if continuation:
            query["continuation"] = continuation
        try:
            payload = get_json(
                self.base_url,
                "/v1/chat-replay/pages",
                query,
                self.bearer_token,
                self.timeout_seconds,
            )
        except GatewayHTTPError as error:
            raise _map_gateway_error(error) from error
        return parse_page(payload, stream_started_at)


def collect_all(
    gateway: ChatReplayGateway,
    video_id: str,
    stream_started_at: datetime,
    report_progress: Callable[[int], None] | None = None,
    start_continuation: str | None = None,
    max_pages: int = 100_000,
) -> tuple[ChatMessage, ...]:
    continuation = start_continuation
    seen_continuations: set[str] = set()
    messages: list[ChatMessage] = []
    for _ in range(max_pages):
        page = gateway.fetch_page(video_id, stream_started_at, continuation)
        messages.extend(page.messages)
        if report_progress:
            report_progress(len(messages))
        continuation = page.continuation
        if continuation is None:
            break
        if continuation in seen_continuations:
            raise ChatReplayProtocolError("chat replay continuation loop detected")
        seen_continuations.add(continuation)
    else:
        raise ChatReplayProtocolError("chat replay page limit exceeded")
    return tuple(sorted(messages, key=lambda item: (item.published_at, item.external_id)))


def parse_page(payload: Any, stream_started_at: datetime) -> ChatPage:
    if not isinstance(payload, dict):
        raise ChatReplayProtocolError("chat replay root must be an object")
    raw_messages = payload.get("messages")
    if not isinstance(raw_messages, list):
        raise ChatReplayProtocolError("chat replay messages are missing")
    continuation = payload.get("continuation")
    if continuation is not None and not isinstance(continuation, str):
        raise ChatReplayProtocolError("invalid chat replay continuation")

    started_at = stream_started_at.astimezone(UTC)
    messages: list[ChatMessage] = []
    for raw in raw_messages:
        if not isinstance(raw, dict):
            raise ChatReplayProtocolError("invalid chat message")
        external_id = raw.get("id")
        author_external_id = raw.get("authorChannelId")
        author_name = raw.get("authorName")
        text = raw.get("text")
        published_value = raw.get("publishedAt")
        if not isinstance(external_id, str) or not external_id:
            raise ChatReplayProtocolError("chat message ID is missing")
        if author_external_id is not None and not isinstance(author_external_id, str):
            raise ChatReplayProtocolError("chat author channel ID is invalid")
        if not isinstance(author_name, str):
            raise ChatReplayProtocolError("chat author name is missing")
        if not isinstance(text, str):
            raise ChatReplayProtocolError("chat message text is missing")
        if not isinstance(published_value, str):
            raise ChatReplayProtocolError("chat message timestamp is missing")
        try:
            published_at = datetime.fromisoformat(published_value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ChatReplayProtocolError("chat message timestamp is invalid") from error
        published_at = published_at.astimezone(UTC)
        elapsed = max(0, int((published_at - started_at).total_seconds() * 1000))
        messages.append(
            ChatMessage(
                external_id=external_id,
                author_external_id=author_external_id,
                author_name=author_name,
                text=text,
                published_at=published_at,
                elapsed_milliseconds=elapsed,
            )
        )
    messages.sort(key=lambda item: (item.published_at, item.external_id))
    return ChatPage(tuple(messages), continuation or None)


def _map_gateway_error(error: GatewayHTTPError) -> ChatReplayError:
    problem = error.problem
    if problem.code == "GATEWAY_UNAUTHORIZED":
        return ChatReplayAuthenticationError(problem.detail)
    if problem.code in {"CHAT_REPLAY_NOT_AVAILABLE", "YOUTUBE_ACCESS_DENIED"}:
        return ChatReplayUnavailable(problem.detail)
    if problem.code == "SOURCE_NOT_READY":
        return ChatReplayNotReady(problem.detail)
    if problem.retryable or problem.code in {
        "YOUTUBE_RATE_LIMITED",
        "YOUTUBE_TEMPORARILY_UNAVAILABLE",
        "YOUTUBE_TIMEOUT",
        "GATEWAY_NOT_READY",
    }:
        return ChatReplayTemporaryError(problem.detail)
    return ChatReplayProtocolError(problem.detail)
