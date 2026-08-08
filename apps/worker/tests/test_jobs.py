from __future__ import annotations

import os
import threading
from datetime import timedelta
from typing import Any
from uuid import uuid4

import psycopg
import pytest

from ysa_worker.jobs import JobRunner, JobStore

DATABASE_URL = os.environ.get("YSA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="YSA_TEST_DATABASE_URL is not set",
)


def required_row(row: tuple[Any, ...] | None) -> tuple[Any, ...]:
    assert row is not None
    return row


def seed_job(step_names: tuple[str, ...] = ("chat_replay",)) -> tuple[str, list[str]]:
    assert DATABASE_URL
    video_id = uuid4().hex[:11]
    with psycopg.connect(DATABASE_URL) as connection:
        stream_id = required_row(
            connection.execute(
                """
                INSERT INTO stream.streams(
                    youtube_video_id,source_url,title,channel_id,channel_title,
                    thumbnail_url,actual_start_at,actual_end_at,duration_seconds
                ) VALUES(%s,%s,'worker test','channel','creator',
                    'https://example.test/t.jpg',now()-interval '1 hour',now(),3600)
                RETURNING id
                """,
                (video_id, f"https://youtu.be/{video_id}"),
            ).fetchone()
        )[0]
        job_id = required_row(
            connection.execute(
                """
                INSERT INTO collection.collection_jobs(
                    stream_id,kind,status,requested_steps
                ) VALUES(%s,'full','queued',%s) RETURNING id
                """,
                (stream_id, list(step_names)),
            ).fetchone()
        )[0]
        step_ids: list[str] = []
        for name in step_names:
            step_id = required_row(
                connection.execute(
                    """
                    INSERT INTO collection.collection_steps(job_id,name,status)
                    VALUES(%s,%s,'queued') RETURNING id
                    """,
                    (job_id, name),
                ).fetchone()
            )[0]
            connection.execute(
                """
                INSERT INTO collection.collection_step_attempts(step_id,attempt,status)
                VALUES(%s,1,'queued')
                """,
                (step_id,),
            )
            step_ids.append(str(step_id))
        return str(job_id), step_ids


def cleanup() -> None:
    assert DATABASE_URL
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("TRUNCATE stream.streams CASCADE")


def test_two_workers_claim_each_step_once() -> None:
    cleanup()
    expected = {seed_job()[1][0], seed_job()[1][0]}
    claimed: list[str] = []
    lock = threading.Lock()

    def claim(worker_id: str) -> None:
        assert DATABASE_URL
        step = JobStore(DATABASE_URL, worker_id, 30).claim()
        assert step is not None
        with lock:
            claimed.append(step.id)

    threads = [
        threading.Thread(target=claim, args=(f"worker-{index}",))
        for index in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert set(claimed) == expected
    assert len(claimed) == len(set(claimed))


def test_runner_persists_progress_and_success() -> None:
    cleanup()
    job_id, step_ids = seed_job()
    assert DATABASE_URL
    store = JobStore(DATABASE_URL, "worker-success", 30)

    def succeed(_step: object, report: Any) -> str:
        report(42)
        return "succeeded"

    runner = JobRunner(store, succeed, heartbeat_seconds=0.05)
    assert runner.run_once() is True
    with psycopg.connect(DATABASE_URL) as connection:
        job = connection.execute(
            "SELECT status,progress_count FROM collection.collection_jobs WHERE id=%s",
            (job_id,),
        ).fetchone()
        step = connection.execute(
            """
            SELECT status,progress_count,worker_id,lease_expires_at
            FROM collection.collection_steps WHERE id=%s
            """,
            (step_ids[0],),
        ).fetchone()
    assert job == ("succeeded", 42)
    assert step == ("succeeded", 42, "worker-success", None)


def test_success_and_failure_are_aggregated_as_partial() -> None:
    cleanup()
    job_id, _step_ids = seed_job(("chat_replay", "transcript"))
    assert DATABASE_URL
    store = JobStore(DATABASE_URL, "worker-partial", 30)

    runner = JobRunner(store, lambda _step, _report: "succeeded", 0.05)
    assert runner.run_once() is True

    class TemporaryFailure(RuntimeError):
        code = "TRANSCRIPT_TEMPORARILY_UNAVAILABLE"
        retryable = True

    def fail(_step: object, _report: object) -> None:
        raise TemporaryFailure("fixture failure")

    runner = JobRunner(store, fail, 0.05)
    assert runner.run_once() is True
    with psycopg.connect(DATABASE_URL) as connection:
        job = connection.execute(
            "SELECT status,progress_count FROM collection.collection_jobs WHERE id=%s",
            (job_id,),
        ).fetchone()
        failed = connection.execute(
            """
            SELECT status,error_code,retryable
            FROM collection.collection_steps
            WHERE job_id=%s AND name='transcript'
            """,
            (job_id,),
        ).fetchone()
    assert job == ("partial", 0)
    assert failed == ("failed", "TRANSCRIPT_TEMPORARILY_UNAVAILABLE", True)


def test_no_data_is_successful_job_completion() -> None:
    cleanup()
    job_id, _step_ids = seed_job(("transcript",))
    assert DATABASE_URL
    runner = JobRunner(
        JobStore(DATABASE_URL, "worker-no-data", 30),
        lambda _step, _report: "no_data",
        0.05,
    )
    assert runner.run_once() is True
    with psycopg.connect(DATABASE_URL) as connection:
        job_status = connection.execute(
            "SELECT status FROM collection.collection_jobs WHERE id=%s",
            (job_id,),
        ).fetchone()
        step_status = connection.execute(
            "SELECT status FROM collection.collection_steps WHERE job_id=%s",
            (job_id,),
        ).fetchone()
    assert job_status == ("succeeded",)
    assert step_status == ("no_data",)


def test_expired_running_step_is_requeued_and_claimed() -> None:
    cleanup()
    job_id, step_ids = seed_job()
    assert DATABASE_URL
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE collection.collection_jobs SET status='running' WHERE id=%s",
            (job_id,),
        )
        connection.execute(
            """
            UPDATE collection.collection_steps
            SET status='running',worker_id='dead-worker',
                lease_expires_at=now()-%s::interval,
                heartbeat_at=now()-%s::interval,
                started_at=now()-%s::interval
            WHERE id=%s
            """,
            (
                timedelta(minutes=5),
                timedelta(minutes=5),
                timedelta(minutes=5),
                step_ids[0],
            ),
        )
        connection.execute(
            """
            UPDATE collection.collection_step_attempts
            SET status='running',worker_id='dead-worker',started_at=now()-interval '5 minutes'
            WHERE step_id=%s AND attempt=1
            """,
            (step_ids[0],),
        )

    store = JobStore(DATABASE_URL, "replacement-worker", 30)
    assert store.recover_expired() == 1
    claimed = store.claim()
    assert claimed is not None
    assert claimed.id == step_ids[0]
