from __future__ import annotations

import logging
import signal
import threading
from datetime import datetime

import psycopg

from ysa_worker.chat_replay import ChatReplayGateway, collect_all
from ysa_worker.chat_storage import ChatMessageRepository
from ysa_worker.config import Settings
from ysa_worker.jobs import ClaimedJob, JobRunner, JobStore, ProgressReporter
from ysa_worker.logging import configure_logging

LOGGER = logging.getLogger("ysa.worker")


def verify_database(database_url: str) -> None:
    with (
        psycopg.connect(database_url, connect_timeout=5) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute("SELECT 1")
        row = cursor.fetchone()
        if row != (1,):
            raise RuntimeError("database self-check returned an unexpected result")


def chat_handler(
    database_url: str,
    gateway: ChatReplayGateway,
    repository: ChatMessageRepository,
    job: ClaimedJob,
    report_progress: ProgressReporter,
) -> None:
    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            """
            SELECT youtube_video_id, actual_start_at
            FROM stream.streams WHERE id=%s
            """,
            (job.stream_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError("stream metadata is missing")
    video_id, started_at = row
    if not isinstance(video_id, str) or not isinstance(started_at, datetime):
        raise RuntimeError("stream metadata is invalid")

    messages = collect_all(gateway, video_id, started_at)
    inserted = repository.save_batch(job.stream_id, job.id, messages)
    report_progress(inserted)
    LOGGER.info(
        "chat replay persisted",
        extra={
            "job_id": job.id,
            "collected_count": len(messages),
            "inserted_count": inserted,
        },
    )


def run(settings: Settings, stop_event: threading.Event) -> None:
    verify_database(settings.database_url)
    gateway = ChatReplayGateway(
        settings.chat_replay_base_url,
        settings.chat_replay_timeout_seconds,
    )
    repository = ChatMessageRepository(settings.database_url)
    store = JobStore(settings.database_url, settings.worker_id, settings.lease_seconds)

    def handle(job: ClaimedJob, report: ProgressReporter) -> None:
        chat_handler(settings.database_url, gateway, repository, job, report)

    runner = JobRunner(store, handle, settings.heartbeat_interval_seconds)
    LOGGER.info("worker ready", extra={"worker_id": settings.worker_id})
    while not stop_event.is_set():
        processed = runner.run_once()
        if not processed:
            stop_event.wait(settings.poll_interval_seconds)
    LOGGER.info("worker stopped", extra={"worker_id": settings.worker_id})


def main() -> None:
    configure_logging()
    settings = Settings.from_environment()
    stop_event = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        LOGGER.info("shutdown requested", extra={"worker_id": settings.worker_id})
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    try:
        run(settings, stop_event)
    except Exception:
        LOGGER.exception("worker startup failed", extra={"worker_id": settings.worker_id})
        raise


if __name__ == "__main__":
    main()
