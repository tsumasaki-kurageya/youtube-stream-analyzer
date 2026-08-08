from __future__ import annotations

import logging
import signal
import threading
from datetime import datetime

import psycopg

from ysa_worker.chat_replay import ChatReplayGateway, collect_all
from ysa_worker.chat_storage import ChatMessageRepository
from ysa_worker.config import Settings
from ysa_worker.jobs import ClaimedStep, JobRunner, JobStore, ProgressReporter, StepOutcome
from ysa_worker.logging import configure_logging
from ysa_worker.reservation_collection import (
    ReservationCollectionRunner,
    ReservationCollectionStore,
)
from ysa_worker.reservation_monitor import (
    ReservationMonitorRunner,
    ReservationStore,
    YouTubeReservationGateway,
)
from ysa_worker.transcript import TranscriptGateway
from ysa_worker.transcript_storage import TranscriptRepository

LOGGER = logging.getLogger("ysa.worker")


class WorkerConfigurationError(RuntimeError):
    code = "WORKER_CONFIGURATION_ERROR"
    retryable = False


def verify_database(database_url: str) -> None:
    with (
        psycopg.connect(database_url, connect_timeout=5) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute("SELECT 1")
        row = cursor.fetchone()
        if row != (1,):
            raise RuntimeError("database self-check returned an unexpected result")


def load_stream(database_url: str, stream_id: str) -> tuple[str, datetime]:
    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            """
            SELECT youtube_video_id, actual_start_at
            FROM stream.streams WHERE id=%s
            """,
            (stream_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError("stream metadata is missing")
    video_id, started_at = row
    if not isinstance(video_id, str) or not isinstance(started_at, datetime):
        raise RuntimeError("stream metadata is invalid")
    return video_id, started_at


def metadata_handler(database_url: str, step: ClaimedStep) -> StepOutcome:
    load_stream(database_url, step.stream_id)
    return "succeeded"


def chat_handler(
    database_url: str,
    gateway: ChatReplayGateway,
    repository: ChatMessageRepository,
    step: ClaimedStep,
    report_progress: ProgressReporter,
) -> StepOutcome:
    video_id, started_at = load_stream(database_url, step.stream_id)
    messages = collect_all(gateway, video_id, started_at)
    inserted = repository.save_batch(step.stream_id, step.job_id, messages)
    report_progress(inserted)
    LOGGER.info(
        "chat replay persisted",
        extra={
            "job_id": step.job_id,
            "step_id": step.id,
            "collected_count": len(messages),
            "inserted_count": inserted,
        },
    )
    return "succeeded"


def transcript_handler(
    database_url: str,
    gateway: TranscriptGateway | None,
    repository: TranscriptRepository,
    step: ClaimedStep,
    report_progress: ProgressReporter,
) -> StepOutcome:
    if gateway is None:
        raise WorkerConfigurationError("YSA_TRANSCRIPT_BASE_URL is required")
    video_id, _started_at = load_stream(database_url, step.stream_id)
    result = gateway.collect(video_id)
    if not result.has_transcript:
        report_progress(0)
        return "no_data"
    saved = repository.replace_complete_result(step.stream_id, step.id, result)
    if saved is None:
        report_progress(0)
        return "no_data"
    report_progress(saved.segment_count)
    LOGGER.info(
        "transcript persisted",
        extra={
            "job_id": step.job_id,
            "step_id": step.id,
            "segment_count": saved.segment_count,
        },
    )
    return "succeeded"


def run(settings: Settings, stop_event: threading.Event) -> None:
    verify_database(settings.database_url)
    chat_gateway = ChatReplayGateway(
        settings.chat_replay_base_url,
        settings.gateway_bearer_token,
        settings.chat_replay_timeout_seconds,
    )
    transcript_gateway = (
        TranscriptGateway(
            settings.transcript_base_url,
            settings.gateway_bearer_token,
            settings.transcript_timeout_seconds,
        )
        if settings.transcript_base_url
        else None
    )
    chat_repository = ChatMessageRepository(settings.database_url)
    transcript_repository = TranscriptRepository(settings.database_url)
    store = JobStore(settings.database_url, settings.worker_id, settings.lease_seconds)

    def handle(step: ClaimedStep, report: ProgressReporter) -> StepOutcome:
        if step.name == "metadata":
            return metadata_handler(settings.database_url, step)
        if step.name == "chat_replay":
            return chat_handler(
                settings.database_url,
                chat_gateway,
                chat_repository,
                step,
                report,
            )
        if step.name == "transcript":
            return transcript_handler(
                settings.database_url,
                transcript_gateway,
                transcript_repository,
                step,
                report,
            )
        raise RuntimeError(f"unsupported collection step: {step.name}")

    job_runner = JobRunner(store, handle, settings.heartbeat_interval_seconds)
    reservation_collection_runner = ReservationCollectionRunner(
        ReservationCollectionStore(settings.database_url)
    )
    reservation_runner = None
    if settings.youtube_api_key:
        reservation_runner = ReservationMonitorRunner(
            ReservationStore(
                settings.database_url,
                settings.worker_id,
                settings.lease_seconds,
            ),
            YouTubeReservationGateway(
                settings.youtube_api_key,
                settings.youtube_api_base_url,
                settings.youtube_timeout_seconds,
            ),
            settings.heartbeat_interval_seconds,
        )

    LOGGER.info("worker ready", extra={"worker_id": settings.worker_id})
    while not stop_event.is_set():
        processed = reservation_collection_runner.run_once()
        if not processed and reservation_runner:
            processed = reservation_runner.run_once()
        if not processed:
            processed = job_runner.run_once()
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
