from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class GatewayProblem:
    status: int
    code: str
    detail: str
    retryable: bool
    retry_after: int | None = None


class GatewayHTTPError(RuntimeError):
    def __init__(self, problem: GatewayProblem) -> None:
        super().__init__(problem.detail)
        self.problem = problem


def get_json(
    base_url: str,
    path: str,
    query: dict[str, str],
    bearer_token: str,
    timeout_seconds: float,
) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {bearer_token}",
            "User-Agent": "ysa-worker/0.1",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.load(response)
    except HTTPError as error:
        raise GatewayHTTPError(_read_problem(error)) from error
    except (TimeoutError, URLError) as error:
        raise GatewayHTTPError(
            GatewayProblem(
                status=503,
                code="YOUTUBE_TEMPORARILY_UNAVAILABLE",
                detail="Gateway request failed",
                retryable=True,
            )
        ) from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise GatewayHTTPError(
            GatewayProblem(
                status=502,
                code="YOUTUBE_SOURCE_CHANGED",
                detail="Gateway returned an invalid JSON response",
                retryable=False,
            )
        ) from error


def _read_problem(error: HTTPError) -> GatewayProblem:
    retry_after = _parse_retry_after(error.headers.get("Retry-After"))
    try:
        payload = json.load(error)
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        return _fallback_problem(error.code, retry_after)
    if not isinstance(payload, dict):
        return _fallback_problem(error.code, retry_after)
    code = payload.get("code")
    retryable = payload.get("retryable")
    detail = payload.get("detail")
    status = payload.get("status")
    if not isinstance(code, str) or not code:
        return _fallback_problem(error.code, retry_after)
    if not isinstance(retryable, bool):
        return _fallback_problem(error.code, retry_after)
    if not isinstance(detail, str) or not detail:
        detail = "Gateway request failed"
    if not isinstance(status, int):
        status = error.code
    return GatewayProblem(status, code, detail, retryable, retry_after)


def _fallback_problem(status: int, retry_after: int | None) -> GatewayProblem:
    if status == 401:
        code = "GATEWAY_UNAUTHORIZED"
        retryable = False
    elif status == 403:
        code = "YOUTUBE_ACCESS_DENIED"
        retryable = False
    elif status == 404:
        code = "TRANSCRIPT_NOT_AVAILABLE"
        retryable = False
    elif status == 409:
        code = "SOURCE_NOT_READY"
        retryable = True
    elif status == 429:
        code = "YOUTUBE_RATE_LIMITED"
        retryable = True
    elif status == 504:
        code = "YOUTUBE_TIMEOUT"
        retryable = True
    elif status >= 500:
        code = "YOUTUBE_TEMPORARILY_UNAVAILABLE"
        retryable = True
    else:
        code = "YOUTUBE_SOURCE_CHANGED"
        retryable = False
    return GatewayProblem(status, code, "Gateway request failed", retryable, retry_after)


def _parse_retry_after(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return max(parsed, 0)
