from __future__ import annotations

import os
import threading
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest

from ysa_worker.chat_replay import ChatMessage
from ysa_worker.chat_storage import ChatMessageRepository

DATABASE_URL = os.environ.get("YSA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="YSA_TEST_DATABASE_URL is not set")


def seed_job() -> tuple[str, str]:
    assert DATABASE_URL
    video_id = uuid4().hex[:11]
    with psycopg.connect(DATABASE_URL) as connection:
        stream_row = connection.execute(
            """
            INSERT INTO stream.streams(
                youtube_video_id, source_url, title, channel_id, channel_title,
                thumbnail_url, actual_start_at, actual_end_at, duration_seconds
            ) VALUES(%s,%s,'chat storage','channel','creator','https://example.test/t.jpg',
                now()-interval '1 hour',now(),3600)
            RETURNING id::text
            """,
            (video_id, f"https://youtu.be/{video_id}"),
        ).fetchone()
        assert stream_row is not None
        job_row = connection.execute(
            """
            INSERT INTO collection.collection_jobs(stream_id,status)
            VALUES(%s,'running') RETURNING id::text
            """,
            (stream_row[0],),
        ).fetchone()
        assert job_row is not None
        return stream_row[0], job_row[0]


def messages() -> tuple[ChatMessage, ...]:
    return (
        ChatMessage("m1", "a1", "Alice", "first", datetime(2026, 1, 1, tzinfo=UTC), 0),
        ChatMessage("m2", None, "Bob", "second", datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC), 1000),
    )


def cleanup() -> None:
    assert DATABASE_URL
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("TRUNCATE stream.streams CASCADE")


def test_save_batch_is_idempotent_and_preserves_existing_data() -> None:
    cleanup()
    stream_id, job_id = seed_job()
    assert DATABASE_URL
    repository = ChatMessageRepository(DATABASE_URL)

    assert repository.save_batch(stream_id, job_id, messages()) == 2
    changed = (
        ChatMessage("m1", "other", "Changed", "changed", datetime.now(UTC), 9999),
    )
    assert repository.save_batch(stream_id, job_id, changed) == 0

    with psycopg.connect(DATABASE_URL) as connection:
        rows = connection.execute(
            """
            SELECT external_message_id,author_name,message_text,elapsed_milliseconds
            FROM chat.chat_messages WHERE stream_id=%s
            ORDER BY elapsed_milliseconds,external_message_id
            """,
            (stream_id,),
        ).fetchall()
    assert rows == [("m1", "Alice", "first", 0), ("m2", "Bob", "second", 1000)]


def test_concurrent_save_does_not_duplicate_messages() -> None:
    cleanup()
    stream_id, job_id = seed_job()
    assert DATABASE_URL
    repository = ChatMessageRepository(DATABASE_URL)
    inserted: list[int] = []
    lock = threading.Lock()

    def save() -> None:
        count = repository.save_batch(stream_id, job_id, messages())
        with lock:
            inserted.append(count)

    threads = [threading.Thread(target=save) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(inserted) == 2
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT count(*) FROM chat.chat_messages WHERE stream_id=%s",
            (stream_id,),
        ).fetchone()
    assert row == (2,)
