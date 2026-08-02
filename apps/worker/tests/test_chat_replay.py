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
    collect_all,
    parse_page,
)

STARTED_AT = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)


def renderer(message_id: str, timestamp_usec: str | None, text: str) -> dict[str, object]:
    value: dict[str, object] = {
        "id": message_id,
        "authorExternalChannelId": f"author-{message_id}",
        "authorName": {"simpleText": f"User {message_id}"},
        "message": {"runs": [{"text": text}]},
    }
    if timestamp_usec is not None:
        value["timestampUsec"] = timestamp_usec
    return {"addChatItemAction": {"item": {"liveChatTextMessageRenderer": value}}}


def test_parse_page_normalizes_time_and_skips_missing_timestamp() -> None:
    payload = {
        "actions": [
            renderer("later", "1767261602000000", "later"),
            renderer("before", "1767261599000000", "before"),
            renderer("missing", None, "missing"),
        ]
    }

    page = parse_page(payload, STARTED_AT)

    assert [message.external_id for message in page.messages] == ["before", "later"]
    assert [message.elapsed_milliseconds for message in page.messages] == [0, 2000]
    assert page.skipped_missing_timestamp == 1


def test_parse_page_rejects_missing_actions() -> None:
    with pytest.raises(ChatReplayProtocolError, match="actions"):
        parse_page({}, STARTED_AT)


def test_collect_all_follows_continuations_and_reports_progress() -> None:
    pages = {
        "": {
            "actions": [renderer("message-2", "1767261602000000", "second")],
            "continuation": "next-page",
        },
        "next-page": {
            "actions": [renderer("message-1", "1767261601000000", "first")],
        },
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
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
            f"http://127.0.0.1:{server.server_port}/replay",
            timeout_seconds=2,
        )
        messages = collect_all(gateway, "video-id", STARTED_AT, progress.append)
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert [message.external_id for message in messages] == ["message-1", "message-2"]
    assert progress == [1, 2]


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
