from __future__ import annotations

import copy
import hashlib
import http.cookiejar
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast

import requests
from requests import Response, Session
from yt_dlp import YoutubeDL
from yt_dlp.extractor.youtube import YoutubeBaseInfoExtractor
from yt_dlp.utils import DownloadError, RegexNotFoundError
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    AgeRestricted,
    CouldNotRetrieveTranscript,
    InvalidVideoId,
    IpBlocked,
    NoTranscriptFound,
    PoTokenRequired,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    VideoUnplayable,
    YouTubeDataUnparsable,
    YouTubeRequestFailed,
)

from .config import Settings
from .core import (
    ChatMessage,
    ChatReplayPage,
    GatewayError,
    TokenCodec,
    TranscriptSegment,
    TranscriptSegmentPage,
    TranscriptTrack,
    TranscriptTrackPage,
)


class ChatProvider(Protocol):
    def get_page(self, video_id: str, continuation: str | None) -> ChatReplayPage: ...

    def ready(self) -> bool: ...


class TranscriptProvider(Protocol):
    def list_tracks(self, video_id: str) -> TranscriptTrackPage: ...

    def get_page(
        self, video_id: str, track_id: str, continuation: str | None
    ) -> TranscriptSegmentPage: ...

    def ready(self) -> bool: ...


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
        self._session = _build_session(settings)

    def ready(self) -> bool:
        return self._settings.readiness_error() is None

    def get_page(self, video_id: str, continuation: str | None) -> ChatReplayPage:
        bootstrap = self._bootstrap(video_id)
        if continuation is None:
            return self._get_first_page(video_id, bootstrap)

        state = self._codec.decode(continuation, "chat")
        if state.get("videoId") != video_id:
            raise _invalid_request("continuation belongs to another video")
        continuation_id = state.get("continuation")
        if not isinstance(continuation_id, str) or not continuation_id:
            raise _invalid_request("chat continuation is invalid")
        offset = state.get("offsetMilliseconds", 0)
        if not isinstance(offset, int) or offset < 0:
            raise _invalid_request("chat continuation offset is invalid")
        click_tracking = state.get("clickTrackingParams")
        if click_tracking is not None and not isinstance(click_tracking, str):
            raise _invalid_request("chat continuation tracking value is invalid")
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
            raise _map_yt_dlp_error(error) from error
        if not isinstance(info, dict):
            raise _source_changed("yt-dlp returned an invalid video result")

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
        webpage = response.text
        extractor = YoutubeBaseInfoExtractor(ydl)
        try:
            initial_data = extractor.extract_yt_initial_data(video_id, webpage)
            ytcfg = extractor.extract_ytcfg(video_id, webpage)
        except RegexNotFoundError as error:
            raise _source_changed("YouTube chat bootstrap data is missing") from error
        if not isinstance(initial_data, dict) or not isinstance(ytcfg, dict):
            raise _source_changed("YouTube chat bootstrap data is invalid")

        initial_continuation = _nested(
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
            raise _source_changed("YouTube Innertube configuration is unavailable")
        visitor_data = _nested(context, "client", "visitorData")
        return _ChatBootstrap(
            api_key=api_key,
            context=cast(dict[str, Any], context),
            visitor_data=visitor_data if isinstance(visitor_data, str) else None,
            initial_continuation=initial_continuation,
            ytcfg=cast(dict[str, Any], ytcfg),
            extractor=extractor,
        )

    def _get_first_page(
        self, video_id: str, bootstrap: _ChatBootstrap
    ) -> ChatReplayPage:
        response = self._request(
            "GET",
            "https://www.youtube.com/live_chat_replay",
            params={"continuation": bootstrap.initial_continuation},
        )
        data = self._parse_chat_response(video_id, bootstrap.extractor, response)
        live_chat = _live_chat_continuation(data)
        refresh = _nested(
            live_chat,
            "header",
            "liveChatHeaderRenderer",
            "viewSelector",
            "sortFilterSubMenuRenderer",
            "subMenuItems",
            1,
            "continuation",
            "reloadContinuationData",
        )
        if isinstance(refresh, dict):
            refresh_id = refresh.get("continuation")
            tracking = refresh.get("trackingParams")
            if isinstance(refresh_id, str) and refresh_id:
                return self._post_page(
                    video_id,
                    bootstrap,
                    refresh_id,
                    0,
                    tracking if isinstance(tracking, str) else None,
                )
        return self._build_chat_page(video_id, live_chat, 0)

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
            f"https://www.youtube.com/youtubei/v1/live_chat/get_live_chat_replay?key={bootstrap.api_key}",
            headers=headers,
            json=payload,
        )
        try:
            data = response.json()
        except requests.JSONDecodeError as error:
            raise _source_changed("YouTube chat response is not JSON") from error
        if not isinstance(data, dict):
            raise _source_changed("YouTube chat response is invalid")
        return self._build_chat_page(video_id, _live_chat_continuation(data), offset)

    def _parse_chat_response(
        self,
        video_id: str,
        extractor: YoutubeBaseInfoExtractor,
        response: Response,
    ) -> dict[str, Any]:
        try:
            initial = extractor.extract_yt_initial_data(video_id, response.text)
            if isinstance(initial, dict):
                return cast(dict[str, Any], initial)
        except RegexNotFoundError:
            pass
        try:
            parsed = response.json()
        except requests.JSONDecodeError as error:
            raise _source_changed("YouTube chat page is invalid") from error
        if not isinstance(parsed, dict):
            raise _source_changed("YouTube chat page is invalid")
        return cast(dict[str, Any], parsed)

    def _build_chat_page(
        self, video_id: str, live_chat: dict[str, Any], previous_offset: int
    ) -> ChatReplayPage:
        messages, observed_offset = normalize_chat_actions(live_chat.get("actions", []))
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
        return ChatReplayPage(
            messages=messages[: self._settings.chat_page_size],
            continuation=next_token,
        )

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
        _raise_for_status(response)
        return response


class YoutubeTranscriptProvider:
    def __init__(
        self,
        settings: Settings,
        codec: TokenCodec,
        transcript_api: Any | None = None,
    ) -> None:
        self._settings = settings
        self._codec = codec
        self._session = _build_session(settings)
        self._api = transcript_api or YouTubeTranscriptApi(http_client=self._session)

    def ready(self) -> bool:
        return self._settings.readiness_error() is None

    def list_tracks(self, video_id: str) -> TranscriptTrackPage:
        try:
            transcript_list = self._api.list(video_id)
            tracks = [self._to_track(video_id, track) for track in transcript_list]
        except TranscriptsDisabled:
            tracks = []
        except CouldNotRetrieveTranscript as error:
            raise _map_transcript_error(error) from error
        return TranscriptTrackPage(tracks=tracks)

    def get_page(
        self, video_id: str, track_id: str, continuation: str | None
    ) -> TranscriptSegmentPage:
        track_payload = self._codec.decode(track_id, "transcript-track")
        if track_payload.get("videoId") != video_id:
            raise _invalid_request("track identifier belongs to another video")

        offset = 0
        if continuation:
            page_payload = self._codec.decode(continuation, "transcript-page")
            if (
                page_payload.get("videoId") != video_id
                or page_payload.get("trackId") != track_id
            ):
                raise _invalid_request("transcript continuation does not match the track")
            raw_offset = page_payload.get("offset")
            if not isinstance(raw_offset, int) or raw_offset < 0:
                raise _invalid_request("transcript continuation offset is invalid")
            offset = raw_offset

        try:
            transcript_list = self._api.list(video_id)
            selected = _select_transcript(transcript_list, track_payload)
            fetched = selected.fetch()
        except (NoTranscriptFound, TranscriptsDisabled):
            raise GatewayError(
                status=404,
                code="TRANSCRIPT_NOT_AVAILABLE",
                detail="transcript is not available",
                retryable=False,
            ) from None
        except CouldNotRetrieveTranscript as error:
            raise _map_transcript_error(error) from error

        all_segments = _normalize_transcript_segments(track_id, fetched)
        page_size = self._settings.transcript_page_size
        page = all_segments[offset : offset + page_size]
        next_offset = offset + len(page)
        next_token = None
        if next_offset < len(all_segments):
            next_token = self._codec.encode(
                "transcript-page",
                {"videoId": video_id, "trackId": track_id, "offset": next_offset},
            )
        return TranscriptSegmentPage(segments=page, continuation=next_token)

    def _to_track(self, video_id: str, track: Any) -> TranscriptTrack:
        language_code = str(track.language_code)
        display_name = str(track.language)
        is_generated = bool(track.is_generated)
        token = self._codec.encode(
            "transcript-track",
            {
                "videoId": video_id,
                "languageCode": language_code,
                "displayName": display_name,
                "isGenerated": is_generated,
            },
        )
        return TranscriptTrack(
            id=token,
            languageCode=language_code,
            displayName=display_name,
            isAutoGenerated=is_generated,
        )


def normalize_chat_actions(actions: Any) -> tuple[list[ChatMessage], int]:
    if not isinstance(actions, list):
        raise _source_changed("YouTube chat actions are invalid")
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
        for nested in nested_actions:
            renderer = _chat_renderer(nested)
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
        authorChannelId=author_channel_id
        if isinstance(author_channel_id, str) and author_channel_id
        else None,
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
    value = _nested(renderer, "accessibility", "accessibilityData", "label")
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
    value = _nested(data, "continuationContents", "liveChatContinuation")
    if not isinstance(value, dict):
        raise _source_changed("YouTube live chat continuation is missing")
    return cast(dict[str, Any], value)


def _select_transcript(transcript_list: Iterable[Any], payload: dict[str, Any]) -> Any:
    for transcript in transcript_list:
        if (
            str(transcript.language_code) == payload.get("languageCode")
            and str(transcript.language) == payload.get("displayName")
            and bool(transcript.is_generated) is payload.get("isGenerated")
        ):
            return transcript
    raise NoTranscriptFound(str(payload.get("videoId", "")), [], transcript_list)


def _normalize_transcript_segments(track_id: str, fetched: Iterable[Any]) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    for index, snippet in enumerate(fetched):
        text = str(snippet.text).strip()
        if not text:
            continue
        start = max(0, round(float(snippet.start) * 1000))
        end = max(start + 1, round((float(snippet.start) + float(snippet.duration)) * 1000))
        digest = hashlib.sha256(
            f"{track_id}\0{index}\0{start}\0{end}\0{text}".encode("utf-8")
        ).hexdigest()
        segments.append(
            TranscriptSegment(
                id=digest,
                startMilliseconds=start,
                endMilliseconds=end,
                text=text[:20000],
            )
        )
    return segments


def _build_session(settings: Settings) -> Session:
    session = requests.Session()
    session.headers.update(
        {
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": "Mozilla/5.0 (compatible; ysa-youtube-data-gateway/0.1)",
        }
    )
    if settings.proxy_url:
        session.proxies.update(
            {"http": settings.proxy_url, "https": settings.proxy_url}
        )
    if settings.cookie_file:
        jar = http.cookiejar.MozillaCookieJar(str(settings.cookie_file))
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
        except (OSError, http.cookiejar.LoadError) as error:
            raise ValueError("YSA_GATEWAY_COOKIE_FILE could not be loaded") from error
        session.cookies.update(jar)
    return session


def _raise_for_status(response: Response) -> None:
    status = response.status_code
    if 200 <= status < 300:
        return
    if status == 429:
        raise GatewayError(
            status=429,
            code="YOUTUBE_RATE_LIMITED",
            detail="YouTube rate limit was reached",
            retryable=True,
            retry_after=120,
        )
    if status in {401, 403}:
        raise GatewayError(
            status=403,
            code="YOUTUBE_ACCESS_DENIED",
            detail="YouTube access was denied",
            retryable=False,
        )
    if status in {404, 410}:
        raise GatewayError(
            status=404,
            code="CHAT_REPLAY_NOT_AVAILABLE",
            detail="chat replay is not available",
            retryable=False,
        )
    if status >= 500:
        raise GatewayError(
            status=503,
            code="YOUTUBE_TEMPORARILY_UNAVAILABLE",
            detail="YouTube is temporarily unavailable",
            retryable=True,
        )
    raise _source_changed("YouTube returned an unexpected response")


def _map_yt_dlp_error(error: DownloadError) -> GatewayError:
    message = str(error).lower()
    if "429" in message or "too many requests" in message:
        return GatewayError(
            status=429,
            code="YOUTUBE_RATE_LIMITED",
            detail="YouTube rate limit was reached",
            retryable=True,
            retry_after=120,
        )
    if any(value in message for value in ("private", "age-restricted", "sign in")):
        return GatewayError(
            status=403,
            code="YOUTUBE_ACCESS_DENIED",
            detail="YouTube access was denied",
            retryable=False,
        )
    if any(value in message for value in ("unavailable", "not available", "removed")):
        return GatewayError(
            status=404,
            code="CHAT_REPLAY_NOT_AVAILABLE",
            detail="chat replay is not available",
            retryable=False,
        )
    return GatewayError(
        status=503,
        code="YOUTUBE_TEMPORARILY_UNAVAILABLE",
        detail="YouTube extraction failed",
        retryable=True,
    )


def _map_transcript_error(error: CouldNotRetrieveTranscript) -> GatewayError:
    if isinstance(error, (RequestBlocked, IpBlocked)):
        return GatewayError(
            status=429,
            code="YOUTUBE_RATE_LIMITED",
            detail="YouTube blocked transcript requests from this network",
            retryable=True,
            retry_after=300,
        )
    if isinstance(error, (AgeRestricted, VideoUnplayable)):
        return GatewayError(
            status=403,
            code="YOUTUBE_ACCESS_DENIED",
            detail="YouTube transcript access was denied",
            retryable=False,
        )
    if isinstance(error, (VideoUnavailable, InvalidVideoId)):
        return GatewayError(
            status=404,
            code="TRANSCRIPT_NOT_AVAILABLE",
            detail="transcript is not available",
            retryable=False,
        )
    if isinstance(error, (YouTubeDataUnparsable, PoTokenRequired)):
        return _source_changed("YouTube transcript source changed")
    if isinstance(error, YouTubeRequestFailed) and "429" in str(error):
        return GatewayError(
            status=429,
            code="YOUTUBE_RATE_LIMITED",
            detail="YouTube rate limit was reached",
            retryable=True,
            retry_after=300,
        )
    return GatewayError(
        status=503,
        code="YOUTUBE_TEMPORARILY_UNAVAILABLE",
        detail="YouTube transcript request failed",
        retryable=True,
    )


def _invalid_request(detail: str) -> GatewayError:
    return GatewayError(
        status=400,
        code="INVALID_REQUEST",
        detail=detail,
        retryable=False,
    )


def _source_changed(detail: str) -> GatewayError:
    return GatewayError(
        status=502,
        code="YOUTUBE_SOURCE_CHANGED",
        detail=detail,
        retryable=False,
    )


def _nested(value: Any, *path: object) -> Any:
    current = value
    for key in path:
        if isinstance(key, int):
            if not isinstance(current, list) or key >= len(current):
                return None
            current = current[key]
        else:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
    return current
