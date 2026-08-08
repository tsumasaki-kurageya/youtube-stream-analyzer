from __future__ import annotations

import os
import threading
from uuid import uuid4

import psycopg
import pytest

from ysa_worker.reservation_collection import ReservationCollectionStore

DATABASE_URL = os.environ.get("YSA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="YSA_TEST_DATABASE_URL is not set",
)


def cleanup() -> None:
    assert DATABASE_URL
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("TRUNCATE stream.streams CASCADE")
        connection.execute("TRUNCATE reservation.reservations CASCADE")


def seed_ready_reservation() -> str:
    assert DATABASE_URL
    video_id = uuid4().hex[:11]
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            """
            INSERT INTO reservation.reservations(
                youtube_video_id,source_url,state,actual_start_at,actual_end_at,
                next_check_at,archive_ready_at,chat_replay_ready_at,
                ready_for_collection_at
            ) VALUES(
                %s,%s,'waiting_for_archive',now()-interval '1 hour',now(),
                now(),now(),now(),now()
            ) RETURNING id::text
            """,
            (video_id, f"https://youtu.be/{video_id}"),
        ).fetchone()
    assert row is not None
    return str(row[0])


def test_ready_reservation_creates_one_full_job_and_steps() -> None:
    cleanup()
    assert DATABASE_URL
    reservation_id = seed_ready_reservation()
    store = ReservationCollectionStore(DATABASE_URL)
    started = store.start_ready()
    assert started is not None and started.reservation_id == reservation_id
    assert store.start_ready() is None

    with psycopg.connect(DATABASE_URL) as connection:
        reservation = connection.execute(
            """
            SELECT state,stream_id::text,collection_job_id::text
            FROM reservation.reservations WHERE id=%s
            """,
            (reservation_id,),
        ).fetchone()
        job = connection.execute(
            """
            SELECT kind,status,requested_steps
            FROM collection.collection_jobs WHERE id=%s
            """,
            (started.job_id,),
        ).fetchone()
        steps = connection.execute(
            """
            SELECT name,status FROM collection.collection_steps
            WHERE job_id=%s ORDER BY name
            """,
            (started.job_id,),
        ).fetchall()
    assert reservation == ("collecting", started.stream_id, started.job_id)
    assert job == ("full", "queued", ["metadata", "chat_replay", "transcript"])
    assert steps == [
        ("chat_replay", "queued"),
        ("metadata", "queued"),
        ("transcript", "queued"),
    ]


def test_two_workers_create_only_one_job() -> None:
    cleanup()
    assert DATABASE_URL
    seed_ready_reservation()
    results: list[str | None] = []
    lock = threading.Lock()

    def start() -> None:
        item = ReservationCollectionStore(DATABASE_URL).start_ready()
        with lock:
            results.append(item.job_id if item else None)

    threads = [threading.Thread(target=start) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len([item for item in results if item is not None]) == 1


def test_succeeded_job_completes_reservation_but_failed_job_does_not() -> None:
    cleanup()
    assert DATABASE_URL
    reservation_id = seed_ready_reservation()
    store = ReservationCollectionStore(DATABASE_URL)
    started = store.start_ready()
    assert started is not None

    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE collection.collection_jobs SET status='failed' WHERE id=%s",
            (started.job_id,),
        )
    assert store.reconcile() == 0
    with psycopg.connect(DATABASE_URL) as connection:
        state = connection.execute(
            "SELECT state FROM reservation.reservations WHERE id=%s",
            (reservation_id,),
        ).fetchone()
    assert state == ("collecting",)

    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE collection.collection_jobs SET status='succeeded' WHERE id=%s",
            (started.job_id,),
        )
    assert store.reconcile() == 1
    with psycopg.connect(DATABASE_URL) as connection:
        completed = connection.execute(
            """
            SELECT state,completed_at IS NOT NULL
            FROM reservation.reservations WHERE id=%s
            """,
            (reservation_id,),
        ).fetchone()
    assert completed == ("completed", True)
