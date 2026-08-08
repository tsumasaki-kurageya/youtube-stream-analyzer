from __future__ import annotations

import json
import signal
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import psycopg

from ysa_worker.config import Settings
from ysa_worker.main import run


class WorkerController:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._stop_event: threading.Event | None = None
        self._worker: threading.Thread | None = None
        self.generation = 0

    def start(self) -> None:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            stop_event = threading.Event()
            self.generation += 1
            worker = threading.Thread(
                target=run,
                args=(self.settings, stop_event),
                daemon=False,
                name=f"e2e-worker-{self.generation}",
            )
            self._stop_event = stop_event
            self._worker = worker
            worker.start()

    def stop(self) -> None:
        with self._lock:
            stop_event = self._stop_event
            worker = self._worker
            self._stop_event = None
            self._worker = None
        if stop_event is not None:
            stop_event.set()
        if worker is not None:
            worker.join(timeout=5)
            if worker.is_alive():
                raise RuntimeError("E2E worker did not stop")

    def restart(self) -> int:
        self.stop()
        self.start()
        return self.generation


class E2EHandler(BaseHTTPRequestHandler):
    controller: WorkerController
    database_url: str

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/health"}:
            self._write_json(HTTPStatus.OK, {"status": "ok"})
            return
        reservation_id = self._reservation_id("/job-count")
        if reservation_id is not None:
            with psycopg.connect(self.database_url) as connection:
                row = connection.execute(
                    """
                    SELECT count(j.id)
                    FROM reservation.reservations r
                    LEFT JOIN collection.collection_jobs j ON j.stream_id=r.stream_id
                    WHERE r.id=%s
                    """,
                    (reservation_id,),
                ).fetchone()
            count = int(row[0]) if row is not None else 0
            self._write_json(HTTPStatus.OK, {"count": count})
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/test/restart-worker":
            generation = self.controller.restart()
            self._write_json(HTTPStatus.OK, {"generation": generation})
            return
        reservation_id = self._reservation_id("/due")
        if reservation_id is not None:
            with psycopg.connect(self.database_url) as connection:
                row = connection.execute(
                    """
                    UPDATE reservation.reservations
                    SET next_check_at=now()-interval '1 second',
                        worker_id=NULL,lease_expires_at=NULL,heartbeat_at=NULL,
                        revision=revision+1,updated_at=now()
                    WHERE id=%s
                    RETURNING state
                    """,
                    (reservation_id,),
                ).fetchone()
            if row is None:
                self._write_json(
                    HTTPStatus.NOT_FOUND,
                    {"error": "reservation_not_found"},
                )
                return
            self._write_json(HTTPStatus.OK, {"state": row[0]})
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def _reservation_id(self, suffix: str) -> str | None:
        prefix = "/test/reservations/"
        if not self.path.startswith(prefix) or not self.path.endswith(suffix):
            return None
        value = self.path[len(prefix) : -len(suffix)]
        return value if value and "/" not in value else None

    def _write_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def main() -> None:
    settings = Settings.from_environment()
    shutdown = threading.Event()
    controller = WorkerController(settings)
    controller.start()

    E2EHandler.controller = controller
    E2EHandler.database_url = settings.database_url
    server = ThreadingHTTPServer(("127.0.0.1", 18082), E2EHandler)
    server.timeout = 0.2

    def stop(_signum: int, _frame: object) -> None:
        shutdown.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        while not shutdown.is_set():
            server.handle_request()
    finally:
        controller.stop()
        server.server_close()


if __name__ == "__main__":
    main()
