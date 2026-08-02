from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    worker_id: str
    poll_interval_seconds: float

    @classmethod
    def from_environment(cls) -> "Settings":
        database_url = os.environ.get("YSA_DATABASE_URL", "").strip()
        if not database_url:
            raise ValueError("YSA_DATABASE_URL is required")

        worker_id = os.environ.get("YSA_WORKER_ID", "local-worker").strip()
        if not worker_id:
            raise ValueError("YSA_WORKER_ID must not be empty")

        raw_interval = os.environ.get("YSA_WORKER_POLL_INTERVAL_SECONDS", "3")
        try:
            poll_interval = float(raw_interval)
        except ValueError as error:
            raise ValueError("YSA_WORKER_POLL_INTERVAL_SECONDS must be numeric") from error
        if poll_interval <= 0:
            raise ValueError("YSA_WORKER_POLL_INTERVAL_SECONDS must be positive")

        return cls(
            database_url=database_url,
            worker_id=worker_id,
            poll_interval_seconds=poll_interval,
        )
