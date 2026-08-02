from __future__ import annotations

import logging
import signal
import threading

import psycopg

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


def pending_chat_handler(_job: ClaimedJob, _report_progress: ProgressReporter) -> None:
    raise RuntimeError("chat replay collector is not implemented yet")


def run(settings: Settings, stop_event: threading.Event) -> None:
    verify_database(settings.database_url)
    store = JobStore(settings.database_url, settings.worker_id, settings.lease_seconds)
    runner = JobRunner(store, pending_chat_handler, settings.heartbeat_interval_seconds)
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
