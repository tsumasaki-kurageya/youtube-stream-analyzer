from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import psycopg
import pytest

from ysa_worker.reservation_monitor import (
    Observation,
    ReservationAccessDenied,
    ReservationStore,
    ReservationTemporaryError,
    YouTubeReservationGateway,
)

DATABASE_URL = os.environ.get("YSA_TEST_DATABASE_URL")


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        video_id = parse_qs(urlparse(self.path).query).get("id", [""])[0]
        if video_id == "temporary01":
            self.send_error(503)
            return
        if video_id == "forbidden01":
            self.send_error(403)
            return
        details: dict[str, str]
        if video_id == "scheduled01":
            details = {"scheduledStartTime": "2030-01-01T00:00:00Z"}
        elif video_id == "livevideo01":
            details = {
                "scheduledStartTime": "2026-01-01T00:00:00Z",
                "actualStartTime": "2026-01-01T00:01:00Z",
            }
        elif video_id == "endedvideo1":
            details = {
                "actualStartTime": "2026-01-01T00:01:00Z",
                "actualEndTime": "2026-01-01T01:01:00Z",
            }
        else:
            details = {}
        body = json.dumps({"items": [{"liveStreamingDetails": details}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


@pytest.fixture
def youtube_url() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


def test_gateway_classifies_stream_states(youtube_url: str) -> None:
    gateway = YouTubeReservationGateway("key", youtube_url)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert gateway.observe("scheduled01", now).state == "scheduled"
    assert gateway.observe("livevideo01", now).state == "live"
    assert gateway.observe("endedvideo1", now).state == "waiting_for_archive"
    assert gateway.observe("monitoring1", now).state == "monitoring"


def test_gateway_classifies_errors(youtube_url: str) -> None:
    gateway = YouTubeReservationGateway("key", youtube_url)
    with pytest.raises(ReservationTemporaryError):
        gateway.observe("temporary01")
    with pytest.raises(ReservationAccessDenied):
        gateway.observe("forbidden01")


def cleanup() -> None:
    if not DATABASE_URL:
        return
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("TRUNCATE reservation.reservations CASCADE")


def seed_reservation(state: str = "monitoring") -> str:
    assert DATABASE_URL
    video_id = uuid4().hex[:11]
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            """
            INSERT INTO reservation.reservations(
                youtube_video_id,source_url,state,next_check_at
            ) VALUES(%s,%s,%s,now()-interval '1 second') RETURNING id::text
            """,
            (video_id, f"https://youtu.be/{video_id}", state),
        ).fetchone()
    assert row is not None
    return str(row[0])


@pytest.mark.skipif(not DATABASE_URL, reason="YSA_TEST_DATABASE_URL is not set")
def test_two_workers_do_not_claim_same_reservation() -> None:
    cleanup()
    expected = {seed_reservation(), seed_reservation()}
    claimed: list[str] = []
    lock = threading.Lock()

    def claim(worker_id: str) -> None:
        assert DATABASE_URL
        item = ReservationStore(DATABASE_URL, worker_id, 30).claim()
        assert item is not None
        with lock:
            claimed.append(item.id)

    threads = [
        threading.Thread(target=claim, args=(f"monitor-{index}",))
        for index in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert set(claimed) == expected
    assert len(claimed) == len(set(claimed))


@pytest.mark.skipif(not DATABASE_URL, reason="YSA_TEST_DATABASE_URL is not set")
def test_state_transition_and_temporary_failure_are_persisted() -> None:
    cleanup()
    assert DATABASE_URL
    reservation_id = seed_reservation()
    store = ReservationStore(DATABASE_URL, "monitor-state", 30)
    claimed = store.claim()
    assert claimed is not None
    observed_at = datetime.now(UTC)
    store.apply(
        claimed,
        Observation(
            "live",
            None,
            observed_at,
            None,
            observed_at + timedelta(seconds=30),
            "stream_live",
        ),
    )
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT state,actual_start_at,worker_id FROM reservation.reservations WHERE id=%s",
            (reservation_id,),
        ).fetchone()
        transition = connection.execute(
            """
            SELECT from_state,to_state,reason_code
            FROM reservation.reservation_transitions
            WHERE reservation_id=%s ORDER BY created_at DESC LIMIT 1
            """,
            (reservation_id,),
        ).fetchone()
    assert row is not None and row[0] == "live" and row[1] is not None and row[2] is None
    assert transition == ("monitoring", "live", "stream_live")

    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            """
            UPDATE reservation.reservations
            SET next_check_at=now()-interval '1 second'
            WHERE id=%s
            """,
            (reservation_id,),
        )
    claimed_again = store.claim()
    assert claimed_again is not None
    store.fail(claimed_again, ReservationTemporaryError("temporary"))
    with psycopg.connect(DATABASE_URL) as connection:
        failed = connection.execute(
            """
            SELECT state,last_error_code,last_error_retryable,next_check_at > now()
            FROM reservation.reservations WHERE id=%s
            """,
            (reservation_id,),
        ).fetchone()
    assert failed == ("live", "YOUTUBE_TEMPORARILY_UNAVAILABLE", True, True)


@pytest.mark.skipif(not DATABASE_URL, reason="YSA_TEST_DATABASE_URL is not set")
def test_expired_lease_is_recovered() -> None:
    cleanup()
    assert DATABASE_URL
    reservation_id = seed_reservation()
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            """
            UPDATE reservation.reservations
            SET worker_id='dead-worker',lease_expires_at=now()-interval '1 second',
                heartbeat_at=now()-interval '2 minutes'
            WHERE id=%s
            """,
            (reservation_id,),
        )
    store = ReservationStore(DATABASE_URL, "replacement-worker", 30)
    assert store.recover_expired() == 1
    claimed = store.claim()
    assert claimed is not None and claimed.id == reservation_id
