from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class TranscriptError(RuntimeError):
    code = "TRANSCRIPT_ERROR"


class TranscriptAccessDenied(TranscriptError):
    code = "TRANSCRIPT_ACCESS_DENIED"


class TranscriptUnavailable(TranscriptError):
    code = "TRANSCRIPT_UNAVAILABLE"


class TranscriptTemporaryError(TranscriptError):
    code = "TRANSCRIPT_TEMPORARILY_UNAVAILABLE"


class TranscriptProtocolError(TranscriptError):
    code = "TRANSCRIPT_SOURCE_CHANGED"


@dataclass(frozen=True)
class TranscriptTrack:
    external_id: str
    language_code: str
    display_name: str
    is_auto_generated: bool


@dataclass(frozen=True)
class TranscriptSegment:
    external_id: str
    start_milliseconds: int
    end_milliseconds: int
    text: str


@dataclass(frozen=True)
class TranscriptResult:
    track: TranscriptTrack | None
    segments: tuple[TranscriptSegment, ...]

    @property
    def has_transcript(self) -> bool:
        return self.track is not None


class TranscriptGateway:
    def __init__(self, base_url: str, timeout_seconds: float = 15) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def collect(self, video_id: str) -> TranscriptResult:
        tracks = self.list_tracks(video_id)
        track = select_track(tracks)
        if track is None:
            return TranscriptResult(track=None, segments=())
        return TranscriptResult(track=track, segments=self.fetch_segments(video_id, track))

    def list_tracks(self, video_id: str) -> tuple[TranscriptTrack, ...]:
        payload = self._get_json("tracks", {"videoId": video_id})
        return parse_tracks(payload)

    def fetch_segments(
        self, video_id: str, track: TranscriptTrack
    ) -> tuple[TranscriptSegment, ...]:
        continuation: str | None = None
        seen: set[str] = set()
        segments: list[TranscriptSegment] = []
        for _ in range(10_000):
            query = {"videoId": video_id, "trackId": track.external_id}
            if continuation:
                query["continuation"] = continuation
            payload = self._get_json("segments", query)
            page, continuation = parse_segment_page(payload)
            segments.extend(page)
            if continuation is None:
                break
            if continuation in seen:
                raise TranscriptProtocolError("transcript continuation loop detected")
            seen.add(continuation)
        else:
            raise TranscriptProtocolError("transcript page limit exceeded")
        return tuple(sorted(segments, key=lambda item: (item.start_milliseconds, item.external_id)))

    def _get_json(self, resource: str, query: dict[str, str]) -> Any:
        request = Request(
            f"{self.base_url}/{resource}?{urlencode(query)}",
            headers={"Accept": "application/json", "User-Agent": "ysa-worker/0.1"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code in {401, 403}:
                raise TranscriptAccessDenied("transcript access was denied") from error
            if error.code in {404, 410, 422}:
                raise TranscriptUnavailable("transcript is unavailable") from error
            if error.code == 429 or error.code >= 500:
                raise TranscriptTemporaryError(
                    "transcript service is temporarily unavailable"
                ) from error
            raise TranscriptProtocolError("unexpected transcript response") from error
        except (TimeoutError, URLError) as error:
            raise TranscriptTemporaryError("transcript request failed") from error
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise TranscriptProtocolError("invalid transcript response") from error


def select_track(tracks: tuple[TranscriptTrack, ...]) -> TranscriptTrack | None:
    if not tracks:
        return None

    def rank(track: TranscriptTrack) -> tuple[int, str, str]:
        is_japanese = track.language_code.lower() == "ja"
        if is_japanese and not track.is_auto_generated:
            priority = 0
        elif is_japanese:
            priority = 1
        elif not track.is_auto_generated:
            priority = 2
        else:
            priority = 3
        return priority, track.language_code.lower(), track.external_id

    return min(tracks, key=rank)


def parse_tracks(payload: Any) -> tuple[TranscriptTrack, ...]:
    if not isinstance(payload, dict):
        raise TranscriptProtocolError("transcript track root must be an object")
    raw_tracks = payload.get("tracks")
    if not isinstance(raw_tracks, list):
        raise TranscriptProtocolError("transcript tracks are missing")
    tracks: list[TranscriptTrack] = []
    for raw in raw_tracks:
        if not isinstance(raw, dict):
            raise TranscriptProtocolError("invalid transcript track")
        external_id = raw.get("id")
        language_code = raw.get("languageCode")
        display_name = raw.get("displayName")
        is_auto_generated = raw.get("isAutoGenerated")
        if not isinstance(external_id, str) or not external_id:
            raise TranscriptProtocolError("transcript track ID is missing")
        if not isinstance(language_code, str) or not language_code:
            raise TranscriptProtocolError("transcript language is missing")
        if not isinstance(display_name, str):
            raise TranscriptProtocolError("transcript display name is missing")
        if not isinstance(is_auto_generated, bool):
            raise TranscriptProtocolError("transcript generation type is missing")
        tracks.append(
            TranscriptTrack(
                external_id=external_id,
                language_code=language_code,
                display_name=display_name,
                is_auto_generated=is_auto_generated,
            )
        )
    return tuple(tracks)


def parse_segment_page(
    payload: Any,
) -> tuple[tuple[TranscriptSegment, ...], str | None]:
    if not isinstance(payload, dict):
        raise TranscriptProtocolError("transcript segment root must be an object")
    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list):
        raise TranscriptProtocolError("transcript segments are missing")
    continuation = payload.get("continuation")
    if continuation is not None and not isinstance(continuation, str):
        raise TranscriptProtocolError("invalid transcript continuation")
    segments: list[TranscriptSegment] = []
    for raw in raw_segments:
        if not isinstance(raw, dict):
            raise TranscriptProtocolError("invalid transcript segment")
        external_id = raw.get("id")
        start = raw.get("startMilliseconds")
        end = raw.get("endMilliseconds")
        text = raw.get("text")
        if not isinstance(external_id, str) or not external_id:
            raise TranscriptProtocolError("transcript segment ID is missing")
        if not isinstance(start, int) or not isinstance(end, int):
            raise TranscriptProtocolError("transcript segment time is missing")
        if start < 0 or end <= start:
            raise TranscriptProtocolError("invalid transcript segment range")
        if not isinstance(text, str):
            raise TranscriptProtocolError("transcript segment text is missing")
        segments.append(
            TranscriptSegment(
                external_id=external_id,
                start_milliseconds=start,
                end_milliseconds=end,
                text=text,
            )
        )
    return tuple(segments), continuation or None
