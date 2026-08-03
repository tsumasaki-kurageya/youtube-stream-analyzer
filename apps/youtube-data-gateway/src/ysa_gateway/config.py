from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    bearer_tokens: tuple[str, ...]
    continuation_secret: str
    request_timeout_seconds: float = 20.0
    chat_page_size: int = 500
    transcript_page_size: int = 1000
    proxy_url: str | None = None
    cookie_file: Path | None = None
    host: str = "0.0.0.0"
    port: int = 8080

    @classmethod
    def from_environment(cls) -> Settings:
        tokens = tuple(
            token.strip()
            for token in os.environ.get("YSA_GATEWAY_TOKENS", "").split(",")
            if token.strip()
        )
        if not tokens:
            raise ValueError("YSA_GATEWAY_TOKENS is required")

        continuation_secret = os.environ.get(
            "YSA_GATEWAY_CONTINUATION_SECRET", ""
        ).strip()
        if len(continuation_secret) < 32:
            raise ValueError(
                "YSA_GATEWAY_CONTINUATION_SECRET must contain at least 32 characters"
            )

        proxy_url = os.environ.get("YSA_GATEWAY_PROXY_URL", "").strip() or None
        cookie_value = os.environ.get("YSA_GATEWAY_COOKIE_FILE", "").strip()
        cookie_file = Path(cookie_value) if cookie_value else None

        return cls(
            bearer_tokens=tokens,
            continuation_secret=continuation_secret,
            request_timeout_seconds=_positive_float(
                "YSA_GATEWAY_REQUEST_TIMEOUT_SECONDS", "20"
            ),
            chat_page_size=_bounded_int("YSA_GATEWAY_CHAT_PAGE_SIZE", "500", 1, 1000),
            transcript_page_size=_bounded_int(
                "YSA_GATEWAY_TRANSCRIPT_PAGE_SIZE", "1000", 1, 5000
            ),
            proxy_url=proxy_url,
            cookie_file=cookie_file,
            host=os.environ.get("YSA_GATEWAY_HOST", "0.0.0.0").strip() or "0.0.0.0",
            port=_bounded_int("PORT", "8080", 1, 65535),
        )

    def readiness_error(self) -> str | None:
        if self.cookie_file is not None and not self.cookie_file.is_file():
            return "configured cookie file does not exist"
        return None


def _positive_float(name: str, default: str) -> float:
    raw = os.environ.get(name, default)
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be numeric") from error
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _bounded_int(name: str, default: str, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, default)
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value
