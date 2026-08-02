from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

LOGGER = logging.getLogger("ysa.worker.reservation.collection")
STEPS = ("metadata", "chat_replay", "transcript")


@dataclass(frozen=True)
class StartedCollection:
    reservation_id: str
    stream_id: str
    job_id: str


class ReservationCollectionStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def start_ready(self) -> StartedCollection | None:
        with (
            psycopg.connect(self.database_url, row_factory=dict_row) as connection,
            connection.transaction(),
        ):
            row = connection.execute(
                """
                SELECT id::text,youtube_video_id,source_url,scheduled_start_at,
                       actual_start_at,actual_end_at
                FROM reservation.reservations
                WHERE state='waiting_for_archive'
                  AND ready_for_collection_at IS NOT NULL
                  AND collection_job_id IS NULL
                ORDER BY ready_for_collection_at,id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None

            stream_id = self._upsert_stream(connection, row)
            job_id = connection.execute(
                """
                INSERT INTO collection.collection_jobs(
                    stream_id,kind,status,requested_steps
                ) VALUES(%s,'full','queued',%s)
                RETURNING id::text
                """,
                (stream_id, list(STEPS)),
            ).fetchone()
            if job_id is None:
                raise RuntimeError("collection job was not created")
            job_id_value = str(job_id["id"])

            for name in STEPS:
                step = connection.execute(
                    """
                    INSERT INTO collection.collection_steps(job_id,name,status)
                    VALUES(%s,%s,'queued') RETURNING id
                    """,
                    (job_id_value, name),
                ).fetchone()
                if step is None:
                    raise RuntimeError("collection step was not created")
                connection.execute(
                    """
                    INSERT INTO collection.collection_step_attempts(step_id,attempt,status)
                    VALUES(%s,1,'queued')
                    """,
                    (step["id"],),
                )

            updated = connection.execute(
                """
                UPDATE reservation.reservations
                SET state='collecting',stream_id=%s,collection_job_id=%s,
                    next_check_at=now(),last_error_code=NULL,last_error_message=NULL,
                    last_error_retryable=NULL,revision=revision+1,updated_at=now()
                WHERE id=%s AND state='waiting_for_archive'
                  AND collection_job_id IS NULL
                RETURNING id::text
                """,
                (stream_id, job_id_value, row["id"]),
            ).fetchone()
            if updated is None:
                raise RuntimeError("reservation collection ownership was lost")
            connection.execute(
                """
                INSERT INTO reservation.reservation_transitions(
                    reservation_id,from_state,to_state,reason_code,detail
                ) VALUES(%s,'waiting_for_archive','collecting',
                         'collection_started',%s)
                """,
                (row["id"], f"collection_job_id={job_id_value}"),
            )
            return StartedCollection(str(row["id"]), stream_id, job_id_value)

    def reconcile(self) -> int:
        with psycopg.connect(self.database_url) as connection, connection.transaction():
            rows = connection.execute(
                """
                UPDATE reservation.reservations r
                SET state='completed',completed_at=COALESCE(completed_at,now()),
                    next_check_at=now(),revision=revision+1,updated_at=now()
                FROM collection.collection_jobs j
                WHERE r.collection_job_id=j.id
                  AND r.state='collecting'
                  AND j.status='succeeded'
                RETURNING r.id
                """
            ).fetchall()
            for row in rows:
                connection.execute(
                    """
                    INSERT INTO reservation.reservation_transitions(
                        reservation_id,from_state,to_state,reason_code
                    ) VALUES(%s,'collecting','completed','collection_succeeded')
                    """,
                    (row[0],),
                )
            return len(rows)

    @staticmethod
    def _upsert_stream(connection: Any, row: dict[str, Any]) -> str:
        actual_start = row["actual_start_at"]
        actual_end = row["actual_end_at"]
        if not isinstance(actual_start, datetime) or not isinstance(actual_end, datetime):
            raise RuntimeError("reservation stream timestamps are incomplete")
        duration = max(0, int((actual_end - actual_start).total_seconds()))
        stored = connection.execute(
            """
            INSERT INTO stream.streams(
                youtube_video_id,source_url,title,channel_id,channel_title,
                thumbnail_url,scheduled_start_at,actual_start_at,actual_end_at,
                duration_seconds
            ) VALUES(%s,%s,%s,'unknown','Unknown','',%s,%s,%s,%s)
            ON CONFLICT (youtube_video_id) DO UPDATE SET
                source_url=EXCLUDED.source_url,
                scheduled_start_at=COALESCE(EXCLUDED.scheduled_start_at,
                                            stream.streams.scheduled_start_at),
                actual_start_at=EXCLUDED.actual_start_at,
                actual_end_at=EXCLUDED.actual_end_at,
                duration_seconds=EXCLUDED.duration_seconds,
                updated_at=now()
            RETURNING id::text
            """,
            (
                row["youtube_video_id"],
                row["source_url"],
                f"YouTube stream {row['youtube_video_id']}",
                row["scheduled_start_at"],
                actual_start,
                actual_end,
                duration,
            ),
        ).fetchone()
        if stored is None:
            raise RuntimeError("stream was not created")
        return str(stored["id"])


class ReservationCollectionRunner:
    def __init__(self, store: ReservationCollectionStore) -> None:
        self.store = store

    def run_once(self) -> bool:
        reconciled = self.store.reconcile()
        started = self.store.start_ready()
        if started is not None:
            LOGGER.info(
                "reservation collection started",
                extra={
                    "reservation_id": started.reservation_id,
                    "stream_id": started.stream_id,
                    "job_id": started.job_id,
                },
            )
        return reconciled > 0 or started is not None
