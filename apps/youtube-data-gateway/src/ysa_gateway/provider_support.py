from __future__ import annotations

import http.cookiejar
from typing import Any

import requests
from requests import Response, Session
from youtube_transcript_api._errors import (
    AgeRestricted,
    CouldNotRetrieveTranscript,
    InvalidVideoId,
    IpBlocked,
    PoTokenRequired,
    RequestBlocked,
    VideoUnavailable,
    VideoUnplayable,
    YouTubeDataUnparsable,
    YouTubeRequestFailed,
)
from yt_dlp.utils import DownloadError

from .config import Settings
from .core import GatewayError


def build_session(settings: Settings) -> Session:
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


def raise_for_youtube_status(response: Response, unavailable_code: str) -> None:
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
            code=unavailable_code,
            detail="requested YouTube data is not available",
            retryable=False,
        )
    if status >= 500:
        raise GatewayError(
            status=503,
            code="YOUTUBE_TEMPORARILY_UNAVAILABLE",
            detail="YouTube is temporarily unavailable",
            retryable=True,
        )
    raise source_changed("YouTube returned an unexpected response")


def map_yt_dlp_error(error: DownloadError) -> GatewayError:
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


def map_transcript_error(error: CouldNotRetrieveTranscript) -> GatewayError:
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
        return source_changed("YouTube transcript source changed")
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


def invalid_request(detail: str) -> GatewayError:
    return GatewayError(
        status=400,
        code="INVALID_REQUEST",
        detail=detail,
        retryable=False,
    )


def source_changed(detail: str) -> GatewayError:
    return GatewayError(
        status=502,
        code="YOUTUBE_SOURCE_CHANGED",
        detail=detail,
        retryable=False,
    )


def nested(value: Any, *path: object) -> Any:
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
