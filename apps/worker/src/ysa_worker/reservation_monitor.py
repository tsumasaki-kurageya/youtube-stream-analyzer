from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import psycopg
from psycopg.rows import dict_row

LOGGER = logging.getLogger("ysa.worker.reservation")

ACTIVE_STATES = ("scheduled", "monitoring", "live", "waiting_for_archive")
ReservationState = Literal["scheduled", "monitoring", "live", "waiting_for_archive"]


class ReservationMonitorError(RuntimeError):
    code = "RESERVATION_MONITORING_FAILED"
    retryable = False


class ReservationTemporaryError(ReservationMonitorError):
    code = "YOUTUBE_TEMPORARILY_UNAVAILABLE"
    retryable = True


class ReservationAccessDenied(ReservationMonitorError):
    code = "YOUTUBE_ACCESS_DENIED"


class ReservationVideoNotFound(ReservationMonitorError):
    code = "RESERVATION_VIDEO_NOT_FOUND"


@dataclass(frozen=True)
class ClaimedReservation:
    id: str
    youtube_video_id: str
    state: str
    scheduled_start_at: datetime | None
    monitor_attempt: int
    revision: int


@dataclass(frozen=True)
class Observation:
    state: ReservationState
    scheduled_start_at: datetime | None
    actual_start_at: datetime | None
    actual_end_at: datetime | None
    next_check_at: datetime
    reason_code: str


class YouTubeReservationGateway:
    def __init__(self, api_key: str, base_url: str, timeout_seconds: float = 10) -> None:
        if not api_key.strip():
            raise ValueError("YSA_YOUTUBE_API_KEY is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def observe(self, video_id: str, now: datetime | None = None) -> Observation:
        current = now or datetime.now(UTC)
        query = urlencode(
            {
                "part": "liveStreamingDetails",
                "id": video_id,
                "key": self.api_key,
            }
        )
        endpoint = f"{self.base_url}/videos?{query}"
        request = Request(
            endpoint,
            headers={"Accept": "application/json", "User-Agent": "ysa-worker/0.1"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.load(response)
        except HTTPError as error:
            if error.code in {401, 403}:
                raise ReservationAccessDenied("YouTube access was denied") from error
            if error.code == 404:
                raise ReservationVideoNotFound("YouTube video was not found") from error
            if error.code == 429 or error.code >= 500:
                raise ReservationTemporaryError("YouTube is temporarily unavailable") from error
            raise ReservationMonitorError("unexpected YouTube response") from error
        except (TimeoutError, URLError, json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ReservationTemporaryError("YouTube reservation check failed") from error

        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise ReservationTemporaryError("invalid YouTube response")
        items = payload["items"]
        if not items:
            raise ReservationVideoNotFound("YouTube video was not found")
        item = items[0]
        if not isinstance(item, dict):
            raise ReservationTemporaryError("invalid YouTube video item")
        details = item.get("liveStreamingDetails")
        if not isinstance(details, dict):
            raise ReservationMonitorError("video is not a live stream")

        scheduled = _parse_time(details.get("scheduledStartTime"))
        actual_start = _parse_time(details.get("actualStartTime"))
        actual_end = _parse_time(details.get("actualEndTime"))
        if actual_end is not None:
            return Observation(
                "waiting_for_archive",
                scheduled,
                actual_start,
                actual_end,
                current + timedelta(minutes=2),
                "stream_ended",
            )
        if actual_start is not None:
            return Observation(
                "live",
                scheduled,
                actual_start,
                None,
                current + timedelta(seconds=30),
                "stream_live",
            )
        if scheduled is not None and scheduled > current + timedelta(minutes=5):
            check_at = min(scheduled - timedelta(minutes=5), current + timedelta(hours=6))
            return Observation(
                "scheduled", scheduled, None, None, check_at, "scheduled_start_wait"
            )
        return Observation(
            "monitoring",
            scheduled,
            None,
            None,
            current + timedelta(minutes=1),
            "stream_not_started",
        )


def _parse_time(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    if not isinstance(value, str):
        raise ReservationTemporaryError("invalid YouTube timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ReservationTemporaryError("invalid YouTube timestamp") from error
    return parsed.astimezone(UTC)


class ReservationStore:
    def __init__(self, database_url: str, worker_id: str, lease_seconds: int) -> None:
        self.database_url = database_url
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds

    def recover_expired(self) -> int:
        with psycopg.connect(self.database_url) as connection:
            result = connection.execute(
                """
                UPDATE reservation.reservations
                SET worker_id=NULL, lease_expires_at=NULL, heartbeat_at=NULL,
                    revision=revision+1, updated_at=now()
                WHERE state=ANY(%s) AND lease_expires_at < now()
                """,
                (list(ACTIVE_STATES),),
            )
            return result.rowcount or 0

    def claim(self) -> ClaimedReservation | None:
        with (
            psycopg.connect(self.database_url, row_factory=dict_row) as connection,
            connection.transaction(),
        ):
            row = connection.execute(
                """
                WITH candidate AS (
                    SELECT id
                    FROM reservation.reservations
                    WHERE state=ANY(%s)
                      AND next_check_at <= now()
                      AND (lease_expires_at IS NULL OR lease_expires_at < now())
                    ORDER BY next_check_at,id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE reservation.reservations r
                SET worker_id=%s, heartbeat_at=now(),
                    lease_expires_at=now()+%s::interval,
                    monitor_attempt=monitor_attempt+1,
                    revision=revision+1, updated_at=now()
                FROM candidate
                WHERE r.id=candidate.id
                RETURNING r.id::text,r.youtube_video_id,r.state,
                          r.scheduled_start_at,r.monitor_attempt,r.revision
                """,
                (
                    list(ACTIVE_STATES),
                    self.worker_id,
                    timedelta(seconds=self.lease_seconds),
                ),
            ).fetchone()
            if row is None:
                return None
            return ClaimedReservation(**row)

    def heartbeat(self, reservation_id: str, revision: int) -> bool:
        with psycopg.connect(self.database_url) as connection:
            result = connection.execute(
                """
                UPDATE reservation.reservations
                SET heartbeat_at=now(),lease_expires_at=now()+%s::interval,updated_at=now()
                WHERE id=%s AND worker_id=%s AND revision=%s
                """,
                (
                    timedelta(seconds=self.lease_seconds),
                    reservation_id,
                    self.worker_id,
                    revision,
                ),
            )
            return result.rowcount == 1

    def apply(self, claimed: ClaimedReservation, observation: Observation) -> None:
        with psycopg.connect(self.database_url) as connection, connection.transaction():
            row = connection.execute(
                """
                UPDATE reservation.reservations
                SET state=%s,scheduled_start_at=COALESCE(%s,scheduled_start_at),
                    actual_start_at=COALESCE(%s,actual_start_at),
                    actual_end_at=COALESCE(%s,actual_end_at),next_check_at=%s,
                    last_checked_at=now(),last_error_code=NULL,last_error_message=NULL,
                    last_error_retryable=NULL,worker_id=NULL,lease_expires_at=NULL,
                    heartbeat_at=NULL,revision=revision+1,updated_at=now()
                WHERE id=%s AND worker_id=%s AND revision=%s
                RETURNING state
                """,
                (
                    observation.state,
                    observation.scheduled_start_at,
                    observation.actual_start_at,
                    observation.actual_end_at,
                    observation.next_check_at,
                    claimed.id,
                    self.worker_id,
                    claimed.revision,
                ),
            ).fetchone()
            if row is None:
                raise RuntimeError("reservation lease is no longer owned")
            if claimed.state != observation.state:
                connection.execute(
                    """
                    INSERT INTO reservation.reservation_transitions(
                        reservation_id,from_state,to_state,reason_code
                    ) VALUES(%s,%s,%s,%s)
                    """,
                    (
                        claimed.id,
                        claimed.state,
                        observation.state,
                        observation.reason_code,
                    ),
                )

    def fail(self, claimed: ClaimedReservation, error: Exception) -> None:
        retryable = bool(getattr(error, "retryable", False))
        code = str(getattr(error, "code", type(error).__name__.upper()))
        if retryable:
            delay = min(60 * (2 ** min(claimed.monitor_attempt - 1, 4)), 900)
            state = claimed.state
            failed_at: datetime | None = None
            next_check = datetime.now(UTC) + timedelta(seconds=delay)
        else:
            state = "failed"
            failed_at = datetime.now(UTC)
            next_check = datetime.now(UTC)
        with psycopg.connect(self.database_url) as connection, connection.transaction():
            result = connection.execute(
                """
                UPDATE reservation.reservations
                SET state=%s,next_check_at=%s,last_checked_at=now(),
                    last_error_code=%s,last_error_message=%s,last_error_retryable=%s,
                    failed_at=%s,worker_id=NULL,lease_expires_at=NULL,heartbeat_at=NULL,
                    revision=revision+1,updated_at=now()
                WHERE id=%s AND worker_id=%s AND revision=%s
                """,
                (
                    state,
                    next_check,
                    code,
                    str(error)[:1000],
                    retryable,
                    failed_at,
                    claimed.id,
                    self.worker_id,
                    claimed.revision,
                ),
            )
            if result.rowcount != 1:
                raise RuntimeError("reservation lease is no longer owned")
            if not retryable:
                connection.execute(
                    """
                    INSERT INTO reservation.reservation_transitions(
                        reservation_id,from_state,to_state,reason_code,
                        error_code,error_message
                    ) VALUES(%s,%s,'failed','monitoring_failed',%s,%s)
                    """,
                    (claimed.id, claimed.state, code, str(error)[:1000]),
                )


class ReservationMonitorRunner:
    def __init__(
        self,
        store: ReservationStore,
        gateway: YouTubeReservationGateway,
        heartbeat_seconds: float,
    ) -> None:
        self.store = store
        self.gateway = gateway
        self.heartbeat_seconds = heartbeat_seconds

    def run_once(self) -> bool:
        self.store.recover_expired()
        claimed = self.store.claim()
        if claimed is None:
            return False
        stop = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat_loop,
            args=(claimed, stop),
            daemon=True,
            name=f"reservation-heartbeat-{claimed.id}",
        )
        heartbeat.start()
        try:
            observation = self.gateway.observe(claimed.youtube_video_id)
            self.store.apply(claimed, observation)
        except Exception as error:
            LOGGER.exception(
                "reservation monitoring failed",
                extra={"reservation_id": claimed.id, "state": claimed.state},
            )
            self.store.fail(claimed, error)
        finally:
            stop.set()
            heartbeat.join(timeout=self.heartbeat_seconds + 1)
        return True

    def _heartbeat_loop(
        self, claimed: ClaimedReservation, stop: threading.Event
    ) -> None:
        while not stop.wait(self.heartbeat_seconds):
            if not self.store.heartbeat(claimed.id, claimed.revision):
                LOGGER.warning(
                    "reservation lease lost", extra={"reservation_id": claimed.id}
                )
                return
