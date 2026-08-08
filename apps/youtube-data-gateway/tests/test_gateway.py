from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from ysa_gateway.app import create_app
from ysa_gateway.chat_provider import YtDlpChatProvider
from ysa_gateway.config import Settings
from ysa_gateway.core import (
    ChatMessage,
    ChatReplayPage,
    GatewayError,
    TokenCodec,
    TranscriptSegmentPage,
    TranscriptTrackPage,
)
from ysa_gateway.providers import (
    YoutubeTranscriptProvider,
    normalize_chat_actions,
)


class FakeChatProvider:
    def ready(self) -> bool:
        return True

    def get_page(self, video_id: str, continuation: str | None) -> ChatReplayPage:
        assert video_id == "abcdefghijk"
        assert continuation is None
        return ChatReplayPage(
            messages=[
                ChatMessage(
                    id="message-1",
                    authorChannelId="channel-1",
                    authorName="Viewer",
                    text="hello",
                    publishedAt=datetime(2026, 8, 3, tzinfo=UTC),
                )
            ],
            continuation=None,
        )


class FakeTranscriptProvider:
    def ready(self) -> bool:
        return True

    def list_tracks(self, video_id: str) -> TranscriptTrackPage:
        assert video_id == "abcdefghijk"
        return TranscriptTrackPage(tracks=[])

    def get_page(
        self, video_id: str, track_id: str, continuation: str | None
    ) -> TranscriptSegmentPage:
        raise AssertionError("not used")


@pytest.fixture
def settings() -> Settings:
    return Settings(
        bearer_tokens=("current-token", "previous-token"),
        continuation_secret="a" * 32,
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    app = create_app(settings, FakeChatProvider(), FakeTranscriptProvider())
    return TestClient(app, raise_server_exceptions=False)


def test_health_and_readiness_do_not_require_authentication(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ok"}


def test_private_endpoint_requires_bearer_token(client: TestClient) -> None:
    response = client.get("/v1/chat-replay/pages?videoId=abcdefghijk")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "GATEWAY_UNAUTHORIZED"
    assert response.json()["retryable"] is False
    assert response.headers["x-request-id"]


def test_current_and_previous_tokens_are_accepted(client: TestClient) -> None:
    for token in ("current-token", "previous-token"):
        response = client.get(
            "/v1/chat-replay/pages?videoId=abcdefghijk",
            headers={"Authorization": f"Bearer {token}", "X-Request-Id": "request-1"},
        )
        assert response.status_code == 200
        assert response.headers["x-request-id"] == "request-1"
        assert response.json() == {
            "messages": [
                {
                    "id": "message-1",
                    "authorChannelId": "channel-1",
                    "authorName": "Viewer",
                    "text": "hello",
                    "publishedAt": "2026-08-03T00:00:00Z",
                }
            ],
            "continuation": None,
        }


def test_first_chat_page_uses_innertube_api_directly(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = YtDlpChatProvider(settings, TokenCodec(settings.continuation_secret))
    bootstrap = type("Bootstrap", (), {"initial_continuation": "initial-token"})()
    monkeypatch.setattr(provider, "_bootstrap", lambda _video_id: bootstrap)

    def reject_legacy_html_request(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("the legacy live_chat_replay HTML endpoint was called")

    monkeypatch.setattr(provider, "_request", reject_legacy_html_request)

    def post_page(
        video_id: str,
        actual_bootstrap: Any,
        continuation_id: str,
        offset: int,
        click_tracking: str | None,
    ) -> ChatReplayPage:
        assert video_id == "abcdefghijk"
        assert actual_bootstrap is bootstrap
        assert continuation_id == "initial-token"
        assert offset == 0
        assert click_tracking is None
        return ChatReplayPage(messages=[], continuation="next-token")

    monkeypatch.setattr(provider, "_post_page", post_page)

    page = provider.get_page("abcdefghijk", None)

    assert page.continuation == "next-token"


def test_validation_errors_use_problem_details(client: TestClient) -> None:
    response = client.get(
        "/v1/chat-replay/pages?videoId=invalid",
        headers={"Authorization": "Bearer current-token"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"


def test_signed_token_rejects_tampering() -> None:
    codec = TokenCodec("b" * 32)
    token = codec.encode("chat", {"videoId": "abcdefghijk", "offset": 10})
    assert codec.decode(token, "chat")["offset"] == 10
    with pytest.raises(GatewayError) as captured:
        codec.decode(token[:-1] + ("A" if token[-1] != "A" else "B"), "chat")
    assert captured.value.code == "INVALID_REQUEST"


def test_chat_actions_are_normalized() -> None:
    actions: list[dict[str, Any]] = [
        {
            "replayChatItemAction": {
                "videoOffsetTimeMsec": "1200",
                "actions": [
                    {
                        "addChatItemAction": {
                            "item": {
                                "liveChatTextMessageRenderer": {
                                    "id": "chat-1",
                                    "timestampUsec": "1785715200000000",
                                    "authorExternalChannelId": "author-1",
                                    "authorName": {"simpleText": "Alice"},
                                    "message": {
                                        "runs": [
                                            {"text": "hello "},
                                            {"emoji": {"shortcuts": [":wave:"]}},
                                        ]
                                    },
                                }
                            }
                        }
                    }
                ],
            }
        }
    ]
    messages, offset = normalize_chat_actions(actions)
    assert offset == 1200
    assert len(messages) == 1
    assert messages[0].id == "chat-1"
    assert messages[0].author_name == "Alice"
    assert messages[0].text == "hello :wave:"


@dataclass
class FakeSnippet:
    text: str
    start: float
    duration: float


class FakeTranscript:
    video_id = "abcdefghijk"
    language = "Japanese"
    language_code = "ja"
    is_generated = True

    def fetch(self) -> list[FakeSnippet]:
        return [
            FakeSnippet("first", 0.0, 1.0),
            FakeSnippet("second", 1.0, 1.5),
        ]


class FakeTranscriptApi:
    def list(self, video_id: str) -> list[FakeTranscript]:
        assert video_id == "abcdefghijk"
        return [FakeTranscript()]


def test_transcript_provider_uses_stable_track_id_and_signed_page_token(
    settings: Settings,
) -> None:
    page_settings = Settings(
        bearer_tokens=settings.bearer_tokens,
        continuation_secret=settings.continuation_secret,
        transcript_page_size=1,
    )
    provider = YoutubeTranscriptProvider(
        page_settings,
        TokenCodec(page_settings.continuation_secret),
        FakeTranscriptApi(),
    )

    tracks = provider.list_tracks("abcdefghijk")
    assert len(tracks.tracks) == 1
    track = tracks.tracks[0]
    assert track.language_code == "ja"
    assert track.is_auto_generated is True

    rotated_provider = YoutubeTranscriptProvider(
        Settings(
            bearer_tokens=settings.bearer_tokens,
            continuation_secret="c" * 32,
        ),
        TokenCodec("c" * 32),
        FakeTranscriptApi(),
    )
    assert rotated_provider.list_tracks("abcdefghijk").tracks[0].id == track.id

    first = provider.get_page("abcdefghijk", track.id, None)
    assert [segment.text for segment in first.segments] == ["first"]
    assert first.continuation is not None

    second = provider.get_page("abcdefghijk", track.id, first.continuation)
    assert [segment.text for segment in second.segments] == ["second"]
    assert second.continuation is None
