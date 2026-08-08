from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

import requests
from requests import Response
from yt_dlp import YoutubeDL
from yt_dlp.extractor.youtube import YoutubeBaseInfoExtractor
from yt_dlp.utils import DownloadError, RegexNotFoundError

from .config import Settings
from .core import ChatMessage, ChatReplayPage, GatewayError, TokenCodec
from .provider_support import (
    build_session,
    invalid_request,
    map_yt_dlp_error,
    nested,
    raise_for_youtube_status,
    source_changed,
)


@dataclass(frozen=True)
class _ChatBootstrap:
    api_key: str
    context: dict[str, Any]
    visitor_data: str | None
    initial_continuation: str
    ytcfg: dict[str, Any]
    extractor: YoutubeBaseInfoExtractor


class YtDlpChatProvider:
    def __init__(self, settings: Settings, codec: TokenCodec) -> None:
        self._settings = settings
        self._codec = codec
        self._session = build_session(settings)

    def ready(self) -> bool:
        return self._settings.readiness_error() is None

    def get_page(self, video_id: str, continuation: str | None) -> ChatReplayPage:
        bootstrap = self._bootstrap(video_id)
        if continuation is None:
            return self._post_page(
                video_id,
                bootstrap,
                bootstrap.initial_continuation,
                0,
                None,
            )

        state = self._codec.decode(continuation, "chat")
        if state.get("videoId") != video_id:
            raise invalid_request("continuation belongs to another video")
        continuation_id = state.get("continuation")
        if not isinstance(continuation_id, str) or not continuation_id:
            raise invalid_request("chat continuation is invalid")
        offset = state.get("offsetMilliseconds", 0)
        if not isinstance(offset, int) or offset < 0:
            raise invalid_request("chat continuation offset is invalid")
        click_tracking = state.get("clickTrackingParams")
        if click_tracking is not None and not isinstance(click_tracking, str):
            raise invalid_request("chat continuation tracking value is invalid")
        return self._post_page(
            video_id,
            bootstrap,
            continuation_id,
            offset,
            click_tracking,
        )

    def _bootstrap(self, video_id: str) -> _ChatBootstrap:
        url = f"https://www.youtube.com/watch?v={video_id}"
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
        }
        if self._settings.proxy_url:
            options["proxy"] = self._settings.proxy_url
        if self._settings.cookie_file:
            options["cookiefile"] = str(self._settings.cookie_file)

        try:
            ydl = YoutubeDL(options)
            info = ydl.extract_info(url, download=False)
        except DownloadError as error:
            raise map_yt_dlp_error(error) from error
        if not isinstance(info, dict):
            raise source_changed("yt-dlp returned an invalid video result")

        subtitles = info.get("subtitles")
        live_chat = subtitles.get("live_chat") if isinstance(subtitles, dict) else None
        if not live_chat:
            live_status = info.get("live_status")
            if live_status in {"is_live", "is_upcoming", "post_live"}:
                raise GatewayError(
                    status=409,
                    code="SOURCE_NOT_READY",
                    detail="chat replay is not ready",
                    retryable=True,
                    retry_after=120,
                )
            raise GatewayError(
                status=404,
                code="CHAT_REPLAY_NOT_AVAILABLE",
                detail="chat replay is not available",
                retryable=False,
            )

        response = self._request("GET", url)
        extractor = YoutubeBaseInfoExtractor(ydl)
        try:
            initial_data = extractor.extract_yt_initial_data(video_id, response.text)
            ytcfg = extractor.extract_ytcfg(video_id, response.text)
        except RegexNotFoundError as error:
            raise source_changed("YouTube chat bootstrap data is missing") from error
        if not isinstance(initial_data, dict) or not isinstance(ytcfg, dict):
            raise source_changed("YouTube chat bootstrap data is invalid")

        initial_continuation = nested(
            initial_data,
            "contents",
            "twoColumnWatchNextResults",
            "conversationBar",
            "liveChatRenderer",
            "continuations",
            0,
            "reloadContinuationData",
            "continuation",
        )
        if not isinstance(initial_continuation, str) or not initial_continuation:
            raise GatewayError(
                status=404,
                code="CHAT_REPLAY_NOT_AVAILABLE",
                detail="chat replay is not available",
                retryable=False,
            )

        api_key = ytcfg.get("INNERTUBE_API_KEY")
        context = ytcfg.get("INNERTUBE_CONTEXT")
        if not isinstance(api_key, str) or not isinstance(context, dict):
            raise source_changed("YouTube Innertube configuration is unavailable")
        visitor_data = nested(context, "client", "visitorData")
        return _ChatBootstrap(
            api_key=api_key,
            context=cast(dict[str, Any], context),
            visitor_data=visitor_data if isinstance(visitor_data, str) else None,
            initial_continuation=initial_continuation,
            ytcfg=cast(dict[str, Any], ytcfg),
            extractor=extractor,
        )

    def _post_page(
        self,
        video_id: str,
        bootstrap: _ChatBootstrap,
        continuation_id: str,
        offset: int,
        click_tracking: str | None,
    ) -> ChatReplayPage:
        context = copy.deepcopy(bootstrap.context)
        if click_tracking:
            context["clickTracking"] = {"clickTrackingParams": click_tracking}
        payload: dict[str, Any] = {
            "context": context,
            "continuation": continuation_id,
            "currentPlayerState": {"playerOffsetMs": str(max(offset - 5000, 0))},
        }
        headers = bootstrap.extractor.generate_api_headers(
            ytcfg=bootstrap.ytcfg,
            visitor_data=bootstrap.visitor_data,
        )
        headers["content-type"] = "application/json"
        response = self._request(
            "POST",
            (
                "https://www.youtube.com/youtubei/v1/live_chat/"
                f"get_live_chat_replay?key={bootstrap.api_key}"
            ),
            headers=headers,
            json=payload,
        )
        try:
            data = response.json()
        except requests.JSONDecodeError as error:
            raise source_changed("YouTube chat response is not JSON") from error
        if not isinstance(data, dict):
            raise source_changed("YouTube chat response is invalid")
        return self._build_chat_page(video_id, _live_chat_continuation(data), offset)

    def _build_chat_page(
        self, video_id: str, live_chat: dict[str, Any], previous_offset: int
    ) -> ChatReplayPage:
        messages, observed_offset = normalize_chat_actions(live_chat.get("actions", []))
        if len(messages) > 1000:
            raise source_changed("YouTube chat page exceeds the gateway contract limit")
        next_id, click_tracking = _next_replay_continuation(live_chat)
        next_token = None
        if next_id:
            next_token = self._codec.encode(
                "chat",
                {
                    "videoId": video_id,
                    "continuation": next_id,
                    "offsetMilliseconds": max(observed_offset, previous_offset),
                    "clickTrackingParams": click_tracking,
                },
            )
        return ChatReplayPage(messages=messages, continuation=next_token)

    def _request(self, method: str, url: str, **kwargs: Any) -> Response:
        try:
            response = self._session.request(
                method,
                url,
                timeout=self._settings.request_timeout_seconds,
                **kwargs,
            )
        except requests.Timeout as error:
            raise GatewayError(
                status=504,
                code="YOUTUBE_TIMEOUT",
                detail="YouTube request timed out",
                retryable=True,
            ) from error
        except requests.RequestException as error:
            raise GatewayError(
                status=503,
                code="YOUTUBE_TEMPORARILY_UNAVAILABLE",
                detail="YouTube request failed",
                retryable=True,
            ) from error
        raise_for_youtube_status(response, "CHAT_REPLAY_NOT_AVAILABLE")
        return response


def normalize_chat_actions(actions: Any) -> tuple[list[ChatMessage], int]:
    if not isinstance(actions, list):
        raise source_changed("YouTube chat actions are invalid")
    messages: list[ChatMessage] = []
    seen_ids: set[str] = set()
    observed_offset = 0
    for action in actions:
        if not isinstance(action, dict):
            continue
        replay = action.get("replayChatItemAction")
        if not isinstance(replay, dict):
            continue
        raw_offset = replay.get("videoOffsetTimeMsec")
        if isinstance(raw_offset, str) and raw_offset.isdigit():
            observed_offset = max(observed_offset, int(raw_offset))
        nested_actions = replay.get("actions")
        if not isinstance(nested_actions, list):
            continue
        for nested_action in nested_actions:
            renderer = _chat_renderer(nested_action)
            if renderer is None:
                continue
            message = _normalize_chat_renderer(renderer)
            if message is None or message.id in seen_ids:
                continue
            seen_ids.add(message.id)
            messages.append(message)
    messages.sort(key=lambda item: (item.published_at, item.id))
    return messages, observed_offset


def _chat_renderer(action: Any) -> dict[str, Any] | None:
    if not isinstance(action, dict):
        return None
    add = action.get("addChatItemAction")
    item = add.get("item") if isinstance(add, dict) else None
    if not isinstance(item, dict):
        return None
    for name in (
        "liveChatTextMessageRenderer",
        "liveChatPaidMessageRenderer",
        "liveChatMembershipItemRenderer",
        "liveChatPaidStickerRenderer",
    ):
        renderer = item.get(name)
        if isinstance(renderer, dict):
            return cast(dict[str, Any], renderer)
    return None


def _normalize_chat_renderer(renderer: dict[str, Any]) -> ChatMessage | None:
    message_id = renderer.get("id")
    timestamp_usec = renderer.get("timestampUsec")
    if not isinstance(message_id, str) or not message_id:
        return None
    if not isinstance(timestamp_usec, str) or not timestamp_usec.isdigit():
        return None
    published_at = datetime.fromtimestamp(int(timestamp_usec) / 1_000_000, UTC)
    author_name = _runs_text(renderer.get("authorName")) or "Unknown"
    author_channel_id = renderer.get("authorExternalChannelId")
    text = (
        _runs_text(renderer.get("message"))
        or _runs_text(renderer.get("headerSubtext"))
        or _runs_text(renderer.get("purchaseAmountText"))
        or _accessibility_text(renderer)
    )
    return ChatMessage(
        id=message_id,
        authorChannelId=(
            author_channel_id
            if isinstance(author_channel_id, str) and author_channel_id
            else None
        ),
        authorName=author_name[:500],
        text=text[:20000],
        publishedAt=published_at,
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
            continue
        emoji = run.get("emoji")
        shortcuts = emoji.get("shortcuts") if isinstance(emoji, dict) else None
        if isinstance(shortcuts, list) and shortcuts and isinstance(shortcuts[0], str):
            parts.append(shortcuts[0])
    return "".join(parts)


def _accessibility_text(renderer: dict[str, Any]) -> str:
    value = nested(renderer, "accessibility", "accessibilityData", "label")
    return value if isinstance(value, str) else ""


def _next_replay_continuation(
    live_chat: dict[str, Any],
) -> tuple[str | None, str | None]:
    continuations = live_chat.get("continuations")
    if not isinstance(continuations, list):
        return None, None
    for item in continuations:
        if not isinstance(item, dict):
            continue
        data = item.get("liveChatReplayContinuationData")
        if not isinstance(data, dict):
            continue
        continuation = data.get("continuation")
        if isinstance(continuation, str) and continuation:
            tracking = data.get("clickTrackingParams")
            return continuation, tracking if isinstance(tracking, str) else None
    return None, None


def _live_chat_continuation(data: dict[str, Any]) -> dict[str, Any]:
    value = nested(data, "continuationContents", "liveChatContinuation")
    if not isinstance(value, dict):
        raise source_changed("YouTube live chat continuation is missing")
    return cast(dict[str, Any], value)
