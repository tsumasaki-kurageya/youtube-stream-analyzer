from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ChatReplayError(RuntimeError):
    code = "CHAT_REPLAY_ERROR"


class ChatReplayUnavailable(ChatReplayError):
    code = "CHAT_REPLAY_UNAVAILABLE"


class ChatReplayTemporaryError(ChatReplayError):
    code = "CHAT_REPLAY_TEMPORARY_ERROR"


class ChatReplayProtocolError(ChatReplayError):
    code = "CHAT_REPLAY_PROTOCOL_CHANGED"


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
    def __init__(self, base_url: str, timeout_seconds: float = 15) -> None:
        self.base_url = base_url.rstrip("/")
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
        request = Request(
            f"{self.base_url}?{urlencode(query)}",
            headers={"Accept": "application/json", "User-Agent": "ysa-worker/0.1"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.load(response)
        except HTTPError as error:
            if error.code in {401, 403, 404, 410}:
                raise ChatReplayUnavailable("chat replay is not available") from error
            if error.code == 429 or error.code >= 500:
                raise ChatReplayTemporaryError(
                    "chat replay service is temporarily unavailable"
                ) from error
            raise ChatReplayProtocolError("unexpected chat replay response") from error
        except (TimeoutError, URLError) as error:
            raise ChatReplayTemporaryError("chat replay request failed") from error
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ChatReplayProtocolError("invalid chat replay response") from error
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
    actions = _find_actions(payload)
    continuation = _find_continuation(payload)
    messages: list[ChatMessage] = []
    skipped = 0
    for renderer in _iter_renderers(actions):
        normalized = _normalize_renderer(renderer, stream_started_at)
        if normalized is None:
            skipped += 1
            continue
        messages.append(normalized)
    messages.sort(key=lambda item: (item.published_at, item.external_id))
    return ChatPage(tuple(messages), continuation, skipped)


def _find_actions(payload: dict[str, Any]) -> list[Any]:
    direct = payload.get("actions")
    if isinstance(direct, list):
        return direct
    continuation = payload.get("continuationContents")
    if isinstance(continuation, dict):
        chat = continuation.get("liveChatContinuation")
        if isinstance(chat, dict) and isinstance(chat.get("actions"), list):
            return chat["actions"]
    raise ChatReplayProtocolError("chat replay actions are missing")


def _find_continuation(payload: dict[str, Any]) -> str | None:
    direct = payload.get("continuation")
    if isinstance(direct, str) and direct:
        return direct
    continuation = payload.get("continuationContents")
    if not isinstance(continuation, dict):
        return None
    chat = continuation.get("liveChatContinuation")
    if not isinstance(chat, dict):
        return None
    values = chat.get("continuations")
    if not isinstance(values, list):
        return None
    for item in values:
        if not isinstance(item, dict):
            continue
        for value in item.values():
            if isinstance(value, dict):
                token = value.get("continuation")
                if isinstance(token, str) and token:
                    return token
    return None


def _iter_renderers(actions: Iterable[Any]) -> Iterable[dict[str, Any]]:
    supported = {
        "liveChatTextMessageRenderer",
        "liveChatPaidMessageRenderer",
        "liveChatMembershipItemRenderer",
    }
    for action in actions:
        if not isinstance(action, dict):
            continue
        replay = action.get("replayChatItemAction")
        candidates = replay.get("actions") if isinstance(replay, dict) else [action]
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            add = candidate.get("addChatItemAction")
            item = add.get("item") if isinstance(add, dict) else None
            if not isinstance(item, dict):
                continue
            for name in supported:
                renderer = item.get(name)
                if isinstance(renderer, dict):
                    yield renderer
                    break


def _normalize_renderer(
    renderer: dict[str, Any], stream_started_at: datetime
) -> ChatMessage | None:
    external_id = renderer.get("id")
    timestamp_usec = renderer.get("timestampUsec")
    if not isinstance(external_id, str) or not external_id:
        raise ChatReplayProtocolError("chat message ID is missing")
    if not isinstance(timestamp_usec, str) or not timestamp_usec.isdigit():
        return None
    published_at = datetime.fromtimestamp(int(timestamp_usec) / 1_000_000, UTC)
    started_at = stream_started_at.astimezone(UTC)
    elapsed = max(0, int((published_at - started_at).total_seconds() * 1000))
    author = renderer.get("authorName")
    author_name = _runs_text(author) or "Unknown"
    author_id = renderer.get("authorExternalChannelId")
    message = renderer.get("message") or renderer.get("headerSubtext")
    text = _runs_text(message)
    return ChatMessage(
        external_id=external_id,
        author_external_id=author_id if isinstance(author_id, str) else None,
        author_name=author_name,
        text=text,
        published_at=published_at,
        elapsed_milliseconds=elapsed,
    )


def _runs_text(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    simple = value.get("simpleText")
    if isinstance(simple, str):
        return simple
    runs = value.get("runs")
    if not isinstance(runs, list):
        return ""
    parts: list[str] = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        text = run.get("text")
        if isinstance(text, str):
            parts.append(text)
        elif isinstance(run.get("emoji"), dict):
            shortcuts = run["emoji"].get("shortcuts")
            if isinstance(shortcuts, list) and shortcuts and isinstance(shortcuts[0], str):
                parts.append(shortcuts[0])
    return "".join(parts)
