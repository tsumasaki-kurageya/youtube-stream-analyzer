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
    gateway_bearer_token: str
    chat_replay_base_url: str
    chat_replay_timeout_seconds: float
    transcript_base_url: str
    transcript_timeout_seconds: float
    youtube_api_key: str
    youtube_api_base_url: str
    youtube_timeout_seconds: float

    @classmethod
    def from_environment(cls) -> Settings:
        database_url = os.environ.get("YSA_DATABASE_URL", "").strip()
        if not database_url:
            raise ValueError("YSA_DATABASE_URL is required")

        worker_id = os.environ.get("YSA_WORKER_ID", "local-worker").strip()
        if not worker_id:
            raise ValueError("YSA_WORKER_ID must not be empty")

        poll_interval = _positive_float("YSA_WORKER_POLL_INTERVAL_SECONDS", "3")
        heartbeat_interval = _positive_float(
            "YSA_WORKER_HEARTBEAT_INTERVAL_SECONDS",
            "30",
        )
        lease_seconds = int(_positive_float("YSA_WORKER_LEASE_SECONDS", "120"))
        if heartbeat_interval >= lease_seconds:
            raise ValueError("heartbeat interval must be shorter than the lease")

        gateway_bearer_token = os.environ.get("YSA_GATEWAY_BEARER_TOKEN", "").strip()
        if not gateway_bearer_token:
            raise ValueError("YSA_GATEWAY_BEARER_TOKEN is required")

        chat_replay_base_url = os.environ.get("YSA_CHAT_REPLAY_BASE_URL", "").strip()
        if not chat_replay_base_url:
            raise ValueError("YSA_CHAT_REPLAY_BASE_URL is required")
        chat_replay_timeout = _positive_float("YSA_CHAT_REPLAY_TIMEOUT_SECONDS", "15")

        transcript_base_url = os.environ.get("YSA_TRANSCRIPT_BASE_URL", "").strip()
        transcript_timeout = _positive_float("YSA_TRANSCRIPT_TIMEOUT_SECONDS", "15")

        youtube_api_key = os.environ.get("YSA_YOUTUBE_API_KEY", "").strip()
        youtube_api_base_url = os.environ.get(
            "YSA_YOUTUBE_API_BASE_URL", "https://www.googleapis.com/youtube/v3"
        ).strip()
        youtube_timeout = _positive_float("YSA_YOUTUBE_TIMEOUT_SECONDS", "10")

        return cls(
            database_url=database_url,
            worker_id=worker_id,
            poll_interval_seconds=poll_interval,
            heartbeat_interval_seconds=heartbeat_interval,
            lease_seconds=lease_seconds,
            gateway_bearer_token=gateway_bearer_token,
            chat_replay_base_url=chat_replay_base_url,
            chat_replay_timeout_seconds=chat_replay_timeout,
            transcript_base_url=transcript_base_url,
            transcript_timeout_seconds=transcript_timeout,
            youtube_api_key=youtube_api_key,
            youtube_api_base_url=youtube_api_base_url,
            youtube_timeout_seconds=youtube_timeout,
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
