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
        video_id = parse_qs(urlparse(self.path).query).get("videoId", [""])[0]
        if self.path.startswith("/videos"):
            video_id = parse_qs(urlparse(self.path).query).get("id", [""])[0]
            if video_id == "failedvideo1":
                status = "failed"
            elif video_id == "processing1":
                status = "uploaded"
            else:
                status = "processed"
            payload = {
                "items": [
                    {
                        "status": {"uploadStatus": status},
                        "contentDetails": {"duration": "PT1H"},
                    }
                ]
            }
        elif video_id == "chatpending1":
            self.send_error(404)
            return
        else:
            payload = {"actions": [], "continuation": None}
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
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
        thread.join()


def test_ready_when_archive_and_chat_are_available(fixture_url: str) -> None:
    gateway = ArchiveReadinessGateway("key", fixture_url, fixture_url)
    now = datetime(2026, 1, 1, 2, tzinfo=UTC)
    result = gateway.check(
        "readyvideo1",
        now - timedelta(hours=2),
        now - timedelta(minutes=10),
        now,
    )
    assert result.state == "ready"
    assert result.archive_ready is True
    assert result.chat_replay_ready is True


def test_processing_archive_and_missing_chat_remain_pending(fixture_url: str) -> None:
    gateway = ArchiveReadinessGateway("key", fixture_url, fixture_url)
    now = datetime(2026, 1, 1, 2, tzinfo=UTC)
    archive = gateway.check(
        "processing1",
        now - timedelta(hours=2),
        now - timedelta(minutes=10),
        now,
    )
    assert archive.state == "pending"
    assert archive.reason_code == "archive_processing"

    chat = gateway.check(
        "chatpending1",
        now - timedelta(hours=2),
        now - timedelta(minutes=10),
        now,
    )
    assert chat.state == "pending"
    assert chat.reason_code == "chat_replay_processing"


def test_permanent_archive_failure_and_timeout_are_distinct(fixture_url: str) -> None:
    gateway = ArchiveReadinessGateway("key", fixture_url, fixture_url)
    now = datetime(2026, 1, 2, 2, tzinfo=UTC)
    with pytest.raises(ArchiveUnavailable):
        gateway.check(
            "failedvideo1",
            now - timedelta(hours=2),
            now - timedelta(minutes=10),
            now,
        )
    with pytest.raises(ArchiveReadinessTimedOut):
        gateway.check(
            "readyvideo1",
            now - timedelta(days=2),
            now - timedelta(hours=25),
            now,
        )
