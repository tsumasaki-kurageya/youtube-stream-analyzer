from __future__ import annotations

import os
import threading
from datetime import timedelta
from uuid import uuid4

import psycopg
import pytest

from ysa_worker.jobs import JobRunner, JobStore

DATABASE_URL = os.environ.get("YSA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="YSA_TEST_DATABASE_URL is not set")


def seed_job() -> str:
    assert DATABASE_URL
    video_id = uuid4().hex[:11]
    with psycopg.connect(DATABASE_URL) as connection:
        stream_id = connection.execute(
            """
            INSERT INTO stream.streams(
                youtube_video_id, source_url, title, channel_id, channel_title,
                thumbnail_url, actual_start_at, actual_end_at, duration_seconds
            ) VALUES(%s,%s,'worker test','channel','creator','https://example.test/t.jpg',
                now()-interval '1 hour',now(),3600)
            RETURNING id
            """,
            (video_id, f"https://youtu.be/{video_id}"),
        ).fetchone()[0]
        job_id = connection.execute(
            "INSERT INTO collection.collection_jobs(stream_id,status) VALUES(%s,'queued') RETURNING id",
            (stream_id,),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO collection.collection_steps(job_id,name,status) VALUES(%s,'chat_replay','queued')",
            (job_id,),
        )
        return str(job_id)


def cleanup() -> None:
    assert DATABASE_URL
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("TRUNCATE stream.streams CASCADE")


def test_two_workers_claim_each_job_once() -> None:
    cleanup()
    job_ids = {seed_job(), seed_job()}
    claimed: list[str] = []
    lock = threading.Lock()

    def claim(worker_id: str) -> None:
        assert DATABASE_URL
        job = JobStore(DATABASE_URL, worker_id, 30).claim()
        assert job is not None
        with lock:
            claimed.append(job.id)

    threads = [threading.Thread(target=claim, args=(f"worker-{index}",)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert set(claimed) == job_ids
    assert len(claimed) == len(set(claimed))


def test_runner_persists_progress_and_success() -> None:
    cleanup()
    job_id = seed_job()
    assert DATABASE_URL
    store = JobStore(DATABASE_URL, "worker-success", 30)
    runner = JobRunner(store, lambda _job, report: report(42), heartbeat_seconds=0.05)

    assert runner.run_once() is True
    with psycopg.connect(DATABASE_URL) as connection:
        row = connection.execute(
            "SELECT status,progress_count,worker_id,lease_expires_at FROM collection.collection_jobs WHERE id=%s",
            (job_id,),
        ).fetchone()
        step = connection.execute(
            "SELECT status,progress_count FROM collection.collection_steps WHERE job_id=%s",
            (job_id,),
        ).fetchone()
    assert row == ("succeeded", 42, "worker-success", None)
    assert step == ("succeeded", 42)


def test_runner_persists_failure_without_exposing_traceback() -> None:
    cleanup()
    job_id = seed_job()
    assert DATABASE_URL

    def fail(_job: object, _report: object) -> None:
        raise ValueError("fixture failure")

    runner = JobRunner(JobStore(DATABASE_URL, "worker-failure", 30), fail, 0.05)
    assert runner.run_once() is True
    with psycopg.connect(DATABASE_URL) as connection:
        status, code, message = connection.execute(
            "SELECT status,error_code,error_message FROM collection.collection_jobs WHERE id=%s",
            (job_id,),
        ).fetchone()
    assert status == "failed"
    assert code == "VALUEERROR"
    assert message == "fixture failure"


def test_expired_running_job_is_requeued_and_claimed() -> None:
    cleanup()
    job_id = seed_job()
    assert DATABASE_URL
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            """
            UPDATE collection.collection_jobs
            SET status='running',worker_id='dead-worker',lease_expires_at=now()-%s::interval,
                heartbeat_at=now()-%s::interval,started_at=now()-%s::interval
            WHERE id=%s
            """,
            (timedelta(minutes=5), timedelta(minutes=5), timedelta(minutes=5), job_id),
        )
        connection.execute(
            "UPDATE collection.collection_steps SET status='running',started_at=now()-interval '5 minutes' WHERE job_id=%s",
            (job_id,),
        )

    store = JobStore(DATABASE_URL, "replacement-worker", 30)
    assert store.recover_expired() == 1
    claimed = store.claim()
    assert claimed is not None
    assert claimed.id == job_id
    with psycopg.connect(DATABASE_URL) as connection:
        status, worker_id = connection.execute(
            "SELECT status,worker_id FROM collection.collection_jobs WHERE id=%s",
            (job_id,),
        ).fetchone()
    assert (status, worker_id) == ("running", "replacement-worker")
