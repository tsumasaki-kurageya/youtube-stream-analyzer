from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from ysa_worker.archive_readiness import (
    ArchiveReadinessGateway,
    ArchiveReadinessTimedOut,
    ArchiveUnavailable,
)


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/videos":
            video_id = query.get("id", [""])[0]
            if video_id == "failedvideo1":
                status = "failed"
            elif video_id == "processing1":
                status = "uploaded"
            else:
                status = "processed"
            self._json(
                {
                    "items": [
                        {
                            "status": {"uploadStatus": status},
                            "contentDetails": {"duration": "PT1H"},
                        }
                    ]
                }
            )
            return

        assert parsed.path == "/v1/chat-replay/pages"
        assert self.headers.get("Authorization") == "Bearer gateway-token"
        video_id = query.get("videoId", [""])[0]
        if video_id == "chatpending1":
            self._problem(409, "SOURCE_NOT_READY", True)
            return
        self._json({"messages": [], "continuation": None})

    def _json(self, payload: object) -> None:
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _problem(self, status: int, code: str, retryable: bool) -> None:
        body = json.dumps(
            {
                "type": f"urn:gateway:{code.lower()}",
                "title": code,
                "status": status,
                "detail": "chat replay is processing",
                "code": code,
                "retryable": retryable,
                "requestId": "request-1",
            }
        ).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/problem+json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


@pytest.fixture
def fixture_url() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def gateway(fixture_url: str) -> ArchiveReadinessGateway:
    return ArchiveReadinessGateway(
        "key",
        fixture_url,
        fixture_url,
        gateway_bearer_token="gateway-token",
    )


def test_ready_when_archive_and_chat_are_available(fixture_url: str) -> None:
    now = datetime(2026, 1, 1, 2, tzinfo=UTC)
    result = gateway(fixture_url).check(
        "readyvideo1",
        now - timedelta(hours=2),
        now - timedelta(minutes=10),
        now,
    )
    assert result.state == "ready"
    assert result.archive_ready is True
    assert result.chat_replay_ready is True


def test_processing_archive_and_missing_chat_remain_pending(fixture_url: str) -> None:
    now = datetime(2026, 1, 1, 2, tzinfo=UTC)
    archive = gateway(fixture_url).check(
        "processing1",
        now - timedelta(hours=2),
        now - timedelta(minutes=10),
        now,
    )
    assert archive.state == "pending"
    assert archive.reason_code == "archive_processing"

    chat = gateway(fixture_url).check(
        "chatpending1",
        now - timedelta(hours=2),
        now - timedelta(minutes=10),
        now,
    )
    assert chat.state == "pending"
    assert chat.reason_code == "chat_replay_processing"


def test_permanent_archive_failure_and_timeout_are_distinct(fixture_url: str) -> None:
    now = datetime(2026, 1, 2, 2, tzinfo=UTC)
    with pytest.raises(ArchiveUnavailable):
        gateway(fixture_url).check(
            "failedvideo1",
            now - timedelta(hours=2),
            now - timedelta(minutes=10),
            now,
        )
    with pytest.raises(ArchiveReadinessTimedOut):
        gateway(fixture_url).check(
            "readyvideo1",
            now - timedelta(days=2),
            now - timedelta(hours=25),
            now,
        )
