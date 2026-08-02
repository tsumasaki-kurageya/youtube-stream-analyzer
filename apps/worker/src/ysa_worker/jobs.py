from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import psycopg
from psycopg.rows import dict_row

LOGGER = logging.getLogger("ysa.worker.jobs")


@dataclass(frozen=True)
class ClaimedJob:
    id: str
    stream_id: str
    attempt: int


class JobStore:
    def __init__(self, database_url: str, worker_id: str, lease_seconds: int) -> None:
        self.database_url = database_url
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds

    def recover_expired(self) -> int:
        with psycopg.connect(self.database_url) as connection:
            result = connection.execute(
                """
                UPDATE collection.collection_jobs
                SET status='queued', worker_id=NULL, lease_expires_at=NULL,
                    heartbeat_at=NULL, started_at=NULL, updated_at=now()
                WHERE status='running' AND lease_expires_at < now()
                """
            )
            connection.execute(
                """
                UPDATE collection.collection_steps s
                SET status='queued', started_at=NULL, updated_at=now()
                FROM collection.collection_jobs j
                WHERE s.job_id=j.id AND j.status='queued' AND s.status='running'
                """
            )
            return result.rowcount or 0

    def claim(self) -> ClaimedJob | None:
        with (
            psycopg.connect(self.database_url, row_factory=dict_row) as connection,
            connection.transaction(),
        ):
            row = connection.execute(
                """
                WITH candidate AS (
                    SELECT id FROM collection.collection_jobs
                    WHERE status='queued'
                    ORDER BY created_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE collection.collection_jobs j
                SET status='running', worker_id=%s, started_at=COALESCE(started_at, now()),
                    heartbeat_at=now(), lease_expires_at=now() + %s::interval,
                    updated_at=now()
                FROM candidate
                WHERE j.id=candidate.id
                RETURNING j.id::text, j.stream_id::text, j.attempt
                """,
                (self.worker_id, timedelta(seconds=self.lease_seconds)),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE collection.collection_steps
                SET status='running', started_at=COALESCE(started_at, now()), updated_at=now()
                WHERE job_id=%s AND name='chat_replay' AND status='queued'
                """,
                (row["id"],),
            )
            return ClaimedJob(**row)

    def heartbeat(self, job_id: str) -> bool:
        with psycopg.connect(self.database_url) as connection:
            result = connection.execute(
                """
                UPDATE collection.collection_jobs
                SET heartbeat_at=now(), lease_expires_at=now() + %s::interval, updated_at=now()
                WHERE id=%s AND status='running' AND worker_id=%s
                """,
                (timedelta(seconds=self.lease_seconds), job_id, self.worker_id),
            )
            return result.rowcount == 1

    def set_progress(self, job_id: str, count: int) -> None:
        if count < 0:
            raise ValueError("progress count must not be negative")
        with psycopg.connect(self.database_url) as connection:
            result = connection.execute(
                """
                UPDATE collection.collection_jobs
                SET progress_count=%s, updated_at=now()
                WHERE id=%s AND status='running' AND worker_id=%s
                """,
                (count, job_id, self.worker_id),
            )
            if result.rowcount != 1:
                raise RuntimeError("job lease is no longer owned")
            connection.execute(
                """
                UPDATE collection.collection_steps
                SET progress_count=%s, updated_at=now()
                WHERE job_id=%s AND name='chat_replay' AND status='running'
                """,
                (count, job_id),
            )

    def succeed(self, job_id: str) -> None:
        self._finish(job_id, "succeeded", None, None)

    def fail(self, job_id: str, code: str, message: str) -> None:
        self._finish(job_id, "failed", code, message[:1000])

    def _finish(self, job_id: str, status: str, code: str | None, message: str | None) -> None:
        with psycopg.connect(self.database_url) as connection:
            result = connection.execute(
                """
                UPDATE collection.collection_jobs
                SET status=%s, error_code=%s, error_message=%s, finished_at=now(),
                    lease_expires_at=NULL, heartbeat_at=now(), updated_at=now()
                WHERE id=%s AND status='running' AND worker_id=%s
                """,
                (status, code, message, job_id, self.worker_id),
            )
            if result.rowcount != 1:
                raise RuntimeError("job lease is no longer owned")
            connection.execute(
                """
                UPDATE collection.collection_steps
                SET status=%s, error_code=%s, error_message=%s, finished_at=now(), updated_at=now()
                WHERE job_id=%s AND name='chat_replay' AND status='running'
                """,
                (status, code, message, job_id),
            )


ProgressReporter = Callable[[int], None]
JobHandler = Callable[[ClaimedJob, ProgressReporter], Any]


class JobRunner:
    def __init__(self, store: JobStore, handler: JobHandler, heartbeat_seconds: float) -> None:
        self.store = store
        self.handler = handler
        self.heartbeat_seconds = heartbeat_seconds

    def run_once(self) -> bool:
        self.store.recover_expired()
        job = self.store.claim()
        if job is None:
            return False

        stop_heartbeat = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat_loop,
            args=(job.id, stop_heartbeat),
            name=f"heartbeat-{job.id}",
            daemon=True,
        )
        heartbeat.start()
        try:
            self.handler(job, lambda count: self.store.set_progress(job.id, count))
            self.store.succeed(job.id)
        except Exception as error:
            LOGGER.exception("job failed", extra={"job_id": job.id})
            code = getattr(error, "code", type(error).__name__.upper())
            self.store.fail(job.id, str(code), str(error))
        finally:
            stop_heartbeat.set()
            heartbeat.join(timeout=self.heartbeat_seconds + 1)
        return True

    def _heartbeat_loop(self, job_id: str, stop: threading.Event) -> None:
        while not stop.wait(self.heartbeat_seconds):
            if not self.store.heartbeat(job_id):
                LOGGER.warning("job lease lost", extra={"job_id": job_id})
                return
