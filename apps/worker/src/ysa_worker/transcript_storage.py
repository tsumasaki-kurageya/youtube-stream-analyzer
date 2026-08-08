from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import psycopg

from ysa_worker.transcript import TranscriptResult, TranscriptSegment, TranscriptTrack


@dataclass(frozen=True)
class TranscriptSaveResult:
    track_id: str
    segment_count: int


class TranscriptRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def replace_complete_result(
        self,
        stream_id: str,
        collection_step_id: str,
        result: TranscriptResult,
        source_etag: str | None = None,
    ) -> TranscriptSaveResult | None:
        if result.track is None:
            return None
        with psycopg.connect(self.database_url) as connection, connection.cursor() as cursor:
            track_id = self._upsert_track(
                cursor,
                stream_id,
                collection_step_id,
                result.track,
                source_etag,
            )
            source_ids = self._upsert_segments(
                cursor,
                stream_id,
                track_id,
                collection_step_id,
                result.segments,
            )
            if source_ids:
                cursor.execute(
                    """
                    DELETE FROM transcript.transcript_segments
                    WHERE track_id = %s AND NOT (source_segment_id = ANY(%s))
                    """,
                    (track_id, source_ids),
                )
            else:
                cursor.execute(
                    "DELETE FROM transcript.transcript_segments WHERE track_id = %s",
                    (track_id,),
                )
            return TranscriptSaveResult(track_id, len(source_ids))

    @staticmethod
    def _upsert_track(
        cursor: psycopg.Cursor[tuple[object, ...]],
        stream_id: str,
        collection_step_id: str,
        track: TranscriptTrack,
        source_etag: str | None,
    ) -> str:
        cursor.execute(
            """
            UPDATE transcript.transcript_tracks
            SET is_selected = false, updated_at = now()
            WHERE stream_id = %s AND is_selected
            """,
            (stream_id,),
        )
        cursor.execute(
            """
            INSERT INTO transcript.transcript_tracks(
                stream_id, external_track_id, language_code, display_name,
                is_auto_generated, is_selected, source_etag, collected_by_step_id
            ) VALUES (%s,%s,%s,%s,%s,true,%s,%s)
            ON CONFLICT (stream_id, external_track_id) DO UPDATE SET
                language_code = EXCLUDED.language_code,
                display_name = EXCLUDED.display_name,
                is_auto_generated = EXCLUDED.is_auto_generated,
                is_selected = true,
                source_etag = EXCLUDED.source_etag,
                collected_by_step_id = EXCLUDED.collected_by_step_id,
                updated_at = now()
            RETURNING id
            """,
            (
                stream_id,
                track.external_id,
                track.language_code,
                track.display_name,
                track.is_auto_generated,
                source_etag,
                collection_step_id,
            ),
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("transcript track upsert returned no row")
        return str(row[0])

    @staticmethod
    def _upsert_segments(
        cursor: psycopg.Cursor[tuple[object, ...]],
        stream_id: str,
        track_id: str,
        collection_step_id: str,
        segments: Iterable[TranscriptSegment],
    ) -> list[str]:
        source_ids: list[str] = []
        for segment in segments:
            source_ids.append(segment.external_id)
            cursor.execute(
                """
                INSERT INTO transcript.transcript_segments(
                    stream_id, track_id, source_segment_id,
                    start_offset_milliseconds, end_offset_milliseconds,
                    text, normalized_text, collected_by_step_id
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (track_id, source_segment_id) DO UPDATE SET
                    start_offset_milliseconds = EXCLUDED.start_offset_milliseconds,
                    end_offset_milliseconds = EXCLUDED.end_offset_milliseconds,
                    text = EXCLUDED.text,
                    normalized_text = EXCLUDED.normalized_text,
                    collected_by_step_id = EXCLUDED.collected_by_step_id,
                    updated_at = now()
                """,
                (
                    stream_id,
                    track_id,
                    segment.external_id,
                    segment.start_milliseconds,
                    segment.end_milliseconds,
                    segment.text,
                    " ".join(segment.text.casefold().split()),
                    collection_step_id,
                ),
            )
        return source_ids
