from __future__ import annotations

import logging
import signal
import threading

import psycopg

from ysa_worker.config import Settings
from ysa_worker.logging import configure_logging

LOGGER = logging.getLogger("ysa.worker")


def verify_database(database_url: str) -> None:
    with psycopg.connect(database_url, connect_timeout=5) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
            if row != (1,):
                raise RuntimeError("database self-check returned an unexpected result")


def run(settings: Settings, stop_event: threading.Event) -> None:
    verify_database(settings.database_url)
    LOGGER.info("worker ready", extra={"worker_id": settings.worker_id})
    while not stop_event.wait(settings.poll_interval_seconds):
        LOGGER.debug("worker heartbeat", extra={"worker_id": settings.worker_id})
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
