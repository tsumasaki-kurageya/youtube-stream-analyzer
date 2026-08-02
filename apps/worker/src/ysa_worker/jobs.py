from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal

import psycopg
from psycopg.rows import dict_row

LOGGER = logging.getLogger("ysa.worker.jobs")


@dataclass(frozen=True)
class ClaimedStep:
    id: str
    job_id: str
    stream_id: str
    name: str
    attempt: int


StepOutcome = Literal["succeeded", "no_data"]
ProgressReporter = Callable[[int], None]
StepHandler = Callable[[ClaimedStep, ProgressReporter], StepOutcome | Any]


def _step_rank_sql(alias: str) -> str:
    return (
        f"CASE {alias}.name "
        "WHEN 'metadata' THEN 1 "
        "WHEN 'chat_replay' THEN 2 "
        "WHEN 'transcript' THEN 3 "
        "ELSE 100 END"
    )


class JobStore:
    def __init__(self, database_url: str, worker_id: str, lease_seconds: int) -> None:
        self.database_url = database_url
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds

    def recover_expired(self) -> int:
        with psycopg.connect(self.database_url) as connection:
            result = connection.execute(
                """
                UPDATE collection.collection_steps
                SET status='queued', worker_id=NULL, lease_expires_at=NULL,
                    heartbeat_at=NULL, started_at=NULL, updated_at=now()
                WHERE status='running' AND lease_expires_at < now()
                """
            )
            connection.execute(
                """
                UPDATE collection.collection_step_attempts a
                SET status='queued', worker_id=NULL, started_at=NULL
                FROM collection.collection_steps s
                WHERE a.step_id=s.id AND a.attempt=s.attempt
                  AND s.status='queued' AND a.status='running'
                """
            )
            self._aggregate_all(connection)
            return result.rowcount or 0

    def claim(self) -> ClaimedStep | None:
        current_rank = _step_rank_sql("s")
        previous_rank = _step_rank_sql("previous")
        query = f"""
            WITH candidate AS (
                SELECT s.id
                FROM collection.collection_steps s
                JOIN collection.collection_jobs j ON j.id=s.job_id
                WHERE s.status='queued'
                  AND NOT EXISTS (
                    SELECT 1 FROM collection.collection_steps previous
                    WHERE previous.job_id=s.job_id
                      AND {previous_rank} < {current_rank}
                      AND previous.status NOT IN ('succeeded','no_data','cancelled')
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM collection.collection_steps active
                    WHERE active.job_id=s.job_id AND active.status='running'
                  )
                ORDER BY j.created_at, {current_rank}, s.id
                FOR UPDATE OF s SKIP LOCKED
                LIMIT 1
            )
            UPDATE collection.collection_steps s
            SET status='running', worker_id=%s,
                started_at=COALESCE(s.started_at,now()), heartbeat_at=now(),
                lease_expires_at=now()+%s::interval, updated_at=now()
            FROM candidate, collection.collection_jobs j
            WHERE s.id=candidate.id AND j.id=s.job_id
            RETURNING s.id::text,s.job_id::text,j.stream_id::text,s.name,s.attempt
        """
        with (
            psycopg.connect(self.database_url, row_factory=dict_row) as connection,
            connection.transaction(),
        ):
            row = connection.execute(
                query,
                (self.worker_id, timedelta(seconds=self.lease_seconds)),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                """
                UPDATE collection.collection_step_attempts
                SET status='running',worker_id=%s,started_at=COALESCE(started_at,now())
                WHERE step_id=%s AND attempt=%s
                """,
                (self.worker_id, row["id"], row["attempt"]),
            )
            connection.execute(
                """
                UPDATE collection.collection_jobs
                SET status='running',started_at=COALESCE(started_at,now()),updated_at=now()
                WHERE id=%s
                """,
                (row["job_id"],),
            )
            return ClaimedStep(**row)

    def heartbeat(self, step_id: str) -> bool:
        with psycopg.connect(self.database_url) as connection:
            result = connection.execute(
                """
                UPDATE collection.collection_steps
                SET heartbeat_at=now(),lease_expires_at=now()+%s::interval,
                    updated_at=now()
                WHERE id=%s AND status='running' AND worker_id=%s
                """,
                (timedelta(seconds=self.lease_seconds), step_id, self.worker_id),
            )
            return result.rowcount == 1

    def set_progress(self, step_id: str, count: int) -> None:
        if count < 0:
            raise ValueError("progress count must not be negative")
        with psycopg.connect(self.database_url) as connection:
            row = connection.execute(
                """
                UPDATE collection.collection_steps
                SET progress_count=%s,updated_at=now()
                WHERE id=%s AND status='running' AND worker_id=%s
                RETURNING job_id,attempt
                """,
                (count, step_id, self.worker_id),
            ).fetchone()
            if row is None:
                raise RuntimeError("step lease is no longer owned")
            job_id, attempt = row
            connection.execute(
                """
                UPDATE collection.collection_step_attempts
                SET progress_count=%s
                WHERE step_id=%s AND attempt=%s
                """,
                (count, step_id, attempt),
            )
            self._aggregate_job(connection, str(job_id))

    def finish(self, step_id: str, status: StepOutcome) -> None:
        self._finish(step_id, status, None, None, None)

    def fail(
        self,
        step_id: str,
        code: str,
        message: str,
        retryable: bool,
    ) -> None:
        self._finish(step_id, "failed", code, message[:1000], retryable)

    def _finish(
        self,
        step_id: str,
        status: str,
        code: str | None,
        message: str | None,
        retryable: bool | None,
    ) -> None:
        with psycopg.connect(self.database_url) as connection:
            row = connection.execute(
                """
                UPDATE collection.collection_steps
                SET status=%s,error_code=%s,error_message=%s,retryable=%s,
                    finished_at=now(),lease_expires_at=NULL,heartbeat_at=now(),
                    updated_at=now()
                WHERE id=%s AND status='running' AND worker_id=%s
                RETURNING job_id,attempt,progress_count
                """,
                (status, code, message, retryable, step_id, self.worker_id),
            ).fetchone()
            if row is None:
                raise RuntimeError("step lease is no longer owned")
            job_id, attempt, progress_count = row
            connection.execute(
                """
                UPDATE collection.collection_step_attempts
                SET status=%s,progress_count=%s,error_code=%s,error_message=%s,
                    retryable=%s,finished_at=now()
                WHERE step_id=%s AND attempt=%s
                """,
                (
                    status,
                    progress_count,
                    code,
                    message,
                    retryable,
                    step_id,
                    attempt,
                ),
            )
            self._aggregate_job(connection, str(job_id))

    @staticmethod
    def _aggregate_job(connection: psycopg.Connection[tuple[Any, ...]], job_id: str) -> None:
        connection.execute(
            """
            WITH aggregate AS (
                SELECT
                    count(*) FILTER (WHERE status IN ('queued','running')) AS active,
                    count(*) FILTER (WHERE status='failed') AS failed,
                    count(*) FILTER (WHERE status IN ('succeeded','no_data')) AS completed,
                    count(*) AS total,
                    coalesce(sum(progress_count),0) AS progress
                FROM collection.collection_steps WHERE job_id=%s
            )
            UPDATE collection.collection_jobs j
            SET status=CASE
                    WHEN a.active > 0 THEN
                        CASE WHEN EXISTS(
                            SELECT 1 FROM collection.collection_steps
                            WHERE job_id=j.id AND status='running'
                        ) THEN 'running' ELSE 'queued' END
                    WHEN a.failed = 0 AND a.completed = a.total THEN 'succeeded'
                    WHEN a.failed > 0 AND a.completed > 0 THEN 'partial'
                    ELSE 'failed'
                END,
                progress_count=a.progress,
                finished_at=CASE WHEN a.active=0 THEN now() ELSE NULL END,
                updated_at=now()
            FROM aggregate a WHERE j.id=%s
            """,
            (job_id, job_id),
        )

    @classmethod
    def _aggregate_all(cls, connection: psycopg.Connection[tuple[Any, ...]]) -> None:
        rows = connection.execute(
            "SELECT DISTINCT job_id::text FROM collection.collection_steps"
        ).fetchall()
        for (job_id,) in rows:
            cls._aggregate_job(connection, job_id)


class JobRunner:
    def __init__(self, store: JobStore, handler: StepHandler, heartbeat_seconds: float) -> None:
        self.store = store
        self.handler = handler
        self.heartbeat_seconds = heartbeat_seconds

    def run_once(self) -> bool:
        self.store.recover_expired()
        step = self.store.claim()
        if step is None:
            return False

        stop_heartbeat = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat_loop,
            args=(step.id, stop_heartbeat),
            name=f"heartbeat-{step.id}",
            daemon=True,
        )
        heartbeat.start()
        try:
            outcome = self.handler(
                step,
                lambda count: self.store.set_progress(step.id, count),
            )
            self.store.finish(step.id, outcome or "succeeded")
        except Exception as error:
            LOGGER.exception(
                "collection step failed",
                extra={"job_id": step.job_id, "step_id": step.id, "step": step.name},
            )
            code = str(getattr(error, "code", type(error).__name__.upper()))
            retryable = bool(
                getattr(
                    error,
                    "retryable",
                    "TEMPORARY" in code or "TEMPORARILY" in code or "TIMEOUT" in code,
                )
            )
            self.store.fail(step.id, code, str(error), retryable)
        finally:
            stop_heartbeat.set()
            heartbeat.join(timeout=self.heartbeat_seconds + 1)
        return True

    def _heartbeat_loop(self, step_id: str, stop: threading.Event) -> None:
        while not stop.wait(self.heartbeat_seconds):
            if not self.store.heartbeat(step_id):
                LOGGER.warning("step lease lost", extra={"step_id": step_id})
                return
