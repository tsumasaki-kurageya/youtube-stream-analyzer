from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    worker_id: str
    poll_interval_seconds: float
    heartbeat_interval_seconds: float
    lease_seconds: int

    @classmethod
    def from_environment(cls) -> Settings:
        database_url = os.environ.get("YSA_DATABASE_URL", "").strip()
        if not database_url:
            raise ValueError("YSA_DATABASE_URL is required")

        worker_id = os.environ.get("YSA_WORKER_ID", "local-worker").strip()
        if not worker_id:
            raise ValueError("YSA_WORKER_ID must not be empty")

        poll_interval = _positive_float("YSA_WORKER_POLL_INTERVAL_SECONDS", "3")
        heartbeat_interval = _positive_float("YSA_WORKER_HEARTBEAT_INTERVAL_SECONDS", "30")
        lease_seconds = int(_positive_float("YSA_WORKER_LEASE_SECONDS", "120"))
        if heartbeat_interval >= lease_seconds:
            raise ValueError("heartbeat interval must be shorter than the lease")

        return cls(
            database_url=database_url,
            worker_id=worker_id,
            poll_interval_seconds=poll_interval,
            heartbeat_interval_seconds=heartbeat_interval,
            lease_seconds=lease_seconds,
        )


def _positive_float(name: str, default: str) -> float:
    raw_value = os.environ.get(name, default)
    try:
        value = float(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be numeric") from error
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value
