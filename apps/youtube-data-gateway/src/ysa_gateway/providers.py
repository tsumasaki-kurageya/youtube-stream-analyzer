from __future__ import annotations

from typing import Protocol

from .chat_provider import YtDlpChatProvider, normalize_chat_actions
from .core import ChatReplayPage, TranscriptSegmentPage, TranscriptTrackPage
from .transcript_provider import YoutubeTranscriptProvider


class ChatProvider(Protocol):
    def get_page(self, video_id: str, continuation: str | None) -> ChatReplayPage: ...

    def ready(self) -> bool: ...


class TranscriptProvider(Protocol):
    def list_tracks(self, video_id: str) -> TranscriptTrackPage: ...

    def get_page(
        self,
        video_id: str,
        track_id: str,
        continuation: str | None,
    ) -> TranscriptSegmentPage: ...

    def ready(self) -> bool: ...


__all__ = [
    "ChatProvider",
    "TranscriptProvider",
    "YoutubeTranscriptProvider",
    "YtDlpChatProvider",
    "normalize_chat_actions",
]
