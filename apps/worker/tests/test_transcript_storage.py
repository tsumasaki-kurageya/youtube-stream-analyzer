from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest

from ysa_worker.transcript import TranscriptResult, TranscriptSegment, TranscriptTrack
from ysa_worker.transcript_storage import TranscriptRepository


@pytest.fixture
def database_url() -> str:
    value = os.getenv("YSA_TEST_DATABASE_URL")
    if not value:
        pytest.skip("YSA_TEST_DATABASE_URL is not set")
    return value


@pytest.fixture
def persisted_context(database_url: str) -> Iterator[tuple[str, str]]:
    video_id = f"tr{uuid.uuid4().hex[:9]}"
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO stream.streams(
                youtube_video_id,source_url,title,channel_id,channel_title,
                thumbnail_url,actual_start_at,actual_end_at,duration_seconds
            ) VALUES (%s,%s,'transcript test','channel','creator',
                'https://example.test/t.jpg',now()-interval '1 hour',now(),3600)
            RETURNING id
            """,
            (video_id, f"https://youtu.be/{video_id}"),
        )
        stream_row = cursor.fetchone()
        if stream_row is None:
            raise RuntimeError("stream insert returned no row")
        stream_id = str(stream_row[0])
        cursor.execute(
            """
            INSERT INTO collection.collection_jobs(stream_id,status)
            VALUES(%s,'succeeded')
            RETURNING id
            """,
            (stream_id,),
        )
        job_row = cursor.fetchone()
        if job_row is None:
            raise RuntimeError("collection job insert returned no row")
        job_id = str(job_row[0])
        cursor.execute(
            """
            INSERT INTO collection.collection_steps(job_id,name,status)
            VALUES(%s,'transcript','succeeded')
            RETURNING id
            """,
            (job_id,),
        )
        step_row = cursor.fetchone()
        if step_row is None:
            raise RuntimeError("collection step insert returned no row")
        step_id = str(step_row[0])
    try:
        yield stream_id, step_id
    finally:
        with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM stream.streams WHERE id=%s", (stream_id,))


def test_replace_complete_result_is_idempotent_and_removes_stale_segments(
    database_url: str, persisted_context: tuple[str, str]
) -> None:
    stream_id, step_id = persisted_context
    repository = TranscriptRepository(database_url)
    track = TranscriptTrack("ja-manual", "ja", "日本語", False)
    first = TranscriptResult(
        track,
        (
            TranscriptSegment("a", 1000, 1800, "first"),
            TranscriptSegment("b", 2000, 2800, "second"),
        ),
    )
    saved = repository.replace_complete_result(stream_id, step_id, first)
    assert saved is not None
    assert saved.segment_count == 2

    second = TranscriptResult(
        track,
        (
            TranscriptSegment("a", 1100, 1900, "updated"),
            TranscriptSegment("c", 3000, 3800, "third"),
        ),
    )
    repository.replace_complete_result(stream_id, step_id, second)

    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT source_segment_id,start_offset_milliseconds,text
            FROM transcript.transcript_segments
            WHERE stream_id=%s ORDER BY source_segment_id
            """,
            (stream_id,),
        )
        assert cursor.fetchall() == [("a", 1100, "updated"), ("c", 3000, "third")]
        cursor.execute(
            """
            SELECT count(*)
            FROM transcript.transcript_tracks
            WHERE stream_id=%s AND is_selected
            """,
            (stream_id,),
        )
        selected_row = cursor.fetchone()
        assert selected_row is not None
        assert selected_row[0] == 1


def test_no_transcript_does_not_modify_existing_data(
    database_url: str, persisted_context: tuple[str, str]
) -> None:
    stream_id, step_id = persisted_context
    repository = TranscriptRepository(database_url)
    repository.replace_complete_result(
        stream_id,
        step_id,
        TranscriptResult(
            TranscriptTrack("ja-manual", "ja", "日本語", False),
            (TranscriptSegment("a", 1000, 1800, "first"),),
        ),
    )
    assert repository.replace_complete_result(
        stream_id, step_id, TranscriptResult(None, ())
    ) is None
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM transcript.transcript_segments WHERE stream_id=%s",
            (stream_id,),
        )
        count_row = cursor.fetchone()
        assert count_row is not None
        assert count_row[0] == 1
