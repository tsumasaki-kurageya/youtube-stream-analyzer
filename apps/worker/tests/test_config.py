from __future__ import annotations

import pytest

from ysa_worker.config import Settings


def test_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YSA_DATABASE_URL", "postgres://example")
    monkeypatch.setenv("YSA_WORKER_ID", "worker-1")
    monkeypatch.setenv("YSA_WORKER_POLL_INTERVAL_SECONDS", "1.5")

    settings = Settings.from_environment()

    assert settings.database_url == "postgres://example"
    assert settings.worker_id == "worker-1"
    assert settings.poll_interval_seconds == 1.5


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("YSA_DATABASE_URL", raising=False)

    with pytest.raises(ValueError, match="YSA_DATABASE_URL"):
        Settings.from_environment()
