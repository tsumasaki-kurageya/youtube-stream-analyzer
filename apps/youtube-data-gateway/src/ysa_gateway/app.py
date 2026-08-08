from __future__ import annotations

import hmac
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import Settings
from .core import (
    ChatReplayPage,
    GatewayError,
    ProbeResponse,
    TokenCodec,
    TranscriptSegmentPage,
    TranscriptTrackPage,
)
from .providers import (
    ChatProvider,
    TranscriptProvider,
    YoutubeTranscriptProvider,
    YtDlpChatProvider,
)

LOGGER = logging.getLogger("ysa.gateway")
_VIDEO_ID_PATTERN = r"^[A-Za-z0-9_-]{11}$"


def create_app(
    settings: Settings | None = None,
    chat_provider: ChatProvider | None = None,
    transcript_provider: TranscriptProvider | None = None,
) -> FastAPI:
    resolved = settings or Settings.from_environment()
    codec = TokenCodec(resolved.continuation_secret)
    chat = chat_provider or YtDlpChatProvider(resolved, codec)
    transcript = transcript_provider or YoutubeTranscriptProvider(resolved, codec)

    app = FastAPI(
        title="YouTube Data Gateway API",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.middleware("http")
    async def request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Any]],
    ) -> Any:
        provided = request.headers.get("x-request-id", "").strip()
        request.state.request_id = provided[:128] if provided else str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response

    @app.exception_handler(GatewayError)
    async def gateway_error_handler(request: Request, error: GatewayError) -> JSONResponse:
        headers: dict[str, str] = {}
        if error.retry_after is not None:
            headers["Retry-After"] = str(error.retry_after)
        return _problem_response(request, error, headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        return _problem_response(
            request,
            GatewayError(
                status=400,
                code="INVALID_REQUEST",
                detail="request parameters are invalid",
                retryable=False,
            ),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
        LOGGER.exception(
            "gateway request failed",
            extra={"request_id": _request_id(request), "path": request.url.path},
        )
        return _problem_response(
            request,
            GatewayError(
                status=500,
                code="INTERNAL_ERROR",
                detail="gateway request failed",
                retryable=False,
            ),
        )

    def authorize(request: Request) -> None:
        header = request.headers.get("authorization", "")
        scheme, separator, token = header.partition(" ")
        if separator != " " or scheme.lower() != "bearer" or not token:
            raise _unauthorized()
        if not any(hmac.compare_digest(token, allowed) for allowed in resolved.bearer_tokens):
            raise _unauthorized()

    @app.get("/healthz", response_model=ProbeResponse)
    def health() -> ProbeResponse:
        return ProbeResponse()

    @app.get("/readyz", response_model=ProbeResponse)
    def readiness() -> ProbeResponse:
        configuration_error = resolved.readiness_error()
        if configuration_error or not chat.ready() or not transcript.ready():
            raise GatewayError(
                status=503,
                code="GATEWAY_NOT_READY",
                detail="gateway configuration or provider is not ready",
                retryable=True,
                retry_after=30,
            )
        return ProbeResponse()

    @app.get(
        "/v1/chat-replay/pages",
        response_model=ChatReplayPage,
        response_model_by_alias=True,
        dependencies=[Depends(authorize)],
    )
    def get_chat_replay_page(
        video_id: str = Query(alias="videoId", pattern=_VIDEO_ID_PATTERN),
        continuation: str | None = Query(default=None, min_length=1, max_length=8192),
    ) -> ChatReplayPage:
        return chat.get_page(video_id, continuation)

    @app.get(
        "/v1/transcripts/tracks",
        response_model=TranscriptTrackPage,
        response_model_by_alias=True,
        dependencies=[Depends(authorize)],
    )
    def list_transcript_tracks(
        video_id: str = Query(alias="videoId", pattern=_VIDEO_ID_PATTERN),
    ) -> TranscriptTrackPage:
        return transcript.list_tracks(video_id)

    @app.get(
        "/v1/transcripts/segments",
        response_model=TranscriptSegmentPage,
        response_model_by_alias=True,
        dependencies=[Depends(authorize)],
    )
    def get_transcript_segments(
        video_id: str = Query(alias="videoId", pattern=_VIDEO_ID_PATTERN),
        track_id: str = Query(alias="trackId", min_length=1, max_length=4096),
        continuation: str | None = Query(default=None, min_length=1, max_length=8192),
    ) -> TranscriptSegmentPage:
        return transcript.get_page(video_id, track_id, continuation)

    return app


def run() -> None:
    settings = Settings.from_environment()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        access_log=False,
    )


def _unauthorized() -> GatewayError:
    return GatewayError(
        status=401,
        code="GATEWAY_UNAUTHORIZED",
        detail="gateway authentication failed",
        retryable=False,
    )


def _problem_response(
    request: Request,
    error: GatewayError,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    response_headers = dict(headers or {})
    response_headers["X-Request-Id"] = request_id
    return JSONResponse(
        status_code=error.status,
        media_type="application/problem+json",
        headers=response_headers,
        content={
            "type": f"urn:youtube-stream-analyzer:gateway:{error.code.lower()}",
            "title": error.code.replace("_", " ").title(),
            "status": error.status,
            "detail": error.detail,
            "code": error.code,
            "retryable": error.retryable,
            "requestId": request_id,
        },
    )


def _request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) and value else str(uuid.uuid4())


if __name__ == "__main__":
    run()
