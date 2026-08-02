from __future__ import annotations

import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ysa_worker.config import Settings
from ysa_worker.main import run


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, _format: str, *_args: object) -> None:
        return


def main() -> None:
    stop_event = threading.Event()
    worker = threading.Thread(
        target=run,
        args=(Settings.from_environment(), stop_event),
        daemon=True,
    )
    worker.start()

    server = ThreadingHTTPServer(("127.0.0.1", 18082), HealthHandler)

    def stop(_signum: int, _frame: object) -> None:
        stop_event.set()
        server.shutdown()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        server.serve_forever()
    finally:
        stop_event.set()
        worker.join(timeout=5)
        server.server_close()


if __name__ == "__main__":
    main()
