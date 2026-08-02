-- +goose Up
CREATE SCHEMA IF NOT EXISTS transcript;

CREATE TABLE transcript.transcript_tracks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    stream_id uuid NOT NULL REFERENCES stream.streams(id) ON DELETE CASCADE,
    external_track_id text NOT NULL,
    language_code text NOT NULL,
    display_name text NOT NULL,
    is_auto_generated boolean NOT NULL,
    is_selected boolean NOT NULL DEFAULT false,
    source_etag text NULL,
    collected_by_step_id uuid NOT NULL REFERENCES collection.collection_steps(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT transcript_tracks_stream_external_uidx UNIQUE (stream_id, external_track_id)
);

CREATE UNIQUE INDEX transcript_tracks_selected_stream_uidx
    ON transcript.transcript_tracks(stream_id)
    WHERE is_selected;

CREATE TABLE transcript.transcript_segments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    stream_id uuid NOT NULL REFERENCES stream.streams(id) ON DELETE CASCADE,
    track_id uuid NOT NULL REFERENCES transcript.transcript_tracks(id) ON DELETE CASCADE,
    source_segment_id text NOT NULL,
    start_offset_milliseconds bigint NOT NULL CHECK (start_offset_milliseconds >= 0),
    end_offset_milliseconds bigint NOT NULL,
    text text NOT NULL CHECK (length(text) > 0),
    normalized_text text NOT NULL,
    collected_by_step_id uuid NOT NULL REFERENCES collection.collection_steps(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT transcript_segments_valid_range CHECK (end_offset_milliseconds > start_offset_milliseconds),
    CONSTRAINT transcript_segments_track_source_uidx UNIQUE (track_id, source_segment_id)
);

CREATE INDEX transcript_segments_stream_time_idx
    ON transcript.transcript_segments(stream_id, start_offset_milliseconds, end_offset_milliseconds, id);
CREATE INDEX transcript_segments_track_time_idx
    ON transcript.transcript_segments(track_id, start_offset_milliseconds, id);

-- +goose Down
DROP SCHEMA IF EXISTS transcript CASCADE;
