from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from ysa_worker.chat_replay import (
    ChatReplayGateway,
    ChatReplayProtocolError,
    ChatReplayTemporaryError,
    collect_all,
    parse_page,
)

STARTED_AT = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)


def message(message_id: str, published_at: str, text: str) -> dict[str, object]:
    return {
        "id": message_id,
        "authorChannelId": f"author-{message_id}",
        "authorName": f"User {message_id}",
        "text": text,
        "publishedAt": published_at,
    }


def test_parse_page_normalizes_elapsed_time() -> None:
    payload = {
        "messages": [
            message("later", "2026-01-01T10:00:02Z", "later"),
            message("before", "2026-01-01T09:59:59Z", "before"),
        ],
        "continuation": None,
    }

    page = parse_page(payload, STARTED_AT)

    assert [item.external_id for item in page.messages] == ["before", "later"]
    assert [item.elapsed_milliseconds for item in page.messages] == [0, 2000]


def test_parse_page_rejects_missing_messages() -> None:
    with pytest.raises(ChatReplayProtocolError, match="messages"):
        parse_page({}, STARTED_AT)


def test_collect_all_follows_continuations_and_sends_authentication() -> None:
    pages = {
        "": {
            "messages": [message("message-2", "2026-01-01T10:00:02Z", "second")],
            "continuation": "next-page",
        },
        "next-page": {
            "messages": [message("message-1", "2026-01-01T10:00:01Z", "first")],
            "continuation": None,
        },
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            assert urlparse(self.path).path == "/v1/chat-replay/pages"
            assert self.headers.get("Authorization") == "Bearer gateway-token"
            query = parse_qs(urlparse(self.path).query)
            continuation = query.get("continuation", [""])[0]
            body = json.dumps(pages[continuation]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    progress: list[int] = []
    try:
        gateway = ChatReplayGateway(
            f"http://127.0.0.1:{server.server_port}",
            "gateway-token",
            timeout_seconds=2,
        )
        messages = collect_all(gateway, "video-id", STARTED_AT, progress.append)
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert [item.external_id for item in messages] == ["message-1", "message-2"]
    assert progress == [1, 2]


def test_problem_details_retryable_error_is_classified() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = json.dumps(
                {
                    "type": "urn:gateway:temporary",
                    "title": "Temporary",
                    "status": 503,
                    "detail": "source is processing",
                    "code": "SOURCE_NOT_READY",
                    "retryable": True,
                    "requestId": "request-1",
                }
            ).encode()
            self.send_response(503)
            self.send_header("Content-Type", "application/problem+json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        gateway = ChatReplayGateway(
            f"http://127.0.0.1:{server.server_port}",
            "gateway-token",
            timeout_seconds=2,
        )
        with pytest.raises(ChatReplayTemporaryError, match="processing"):
            gateway.fetch_page("video-id", STARTED_AT)
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_collect_all_detects_continuation_loop() -> None:
    class LoopGateway:
        def fetch_page(
            self,
            _video_id: str,
            _stream_started_at: datetime,
            _continuation: str | None = None,
        ) -> object:
            from ysa_worker.chat_replay import ChatPage

            return ChatPage((), "same")

    with pytest.raises(ChatReplayProtocolError, match="loop"):
        collect_all(LoopGateway(), "video-id", STARTED_AT)  # type: ignore[arg-type]
