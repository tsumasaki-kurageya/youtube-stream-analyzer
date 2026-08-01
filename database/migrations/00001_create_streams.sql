-- +goose Up
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS stream;

CREATE TABLE stream.streams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    youtube_video_id VARCHAR(11) NOT NULL UNIQUE,
    source_url TEXT NOT NULL,
    title TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    channel_title TEXT NOT NULL,
    thumbnail_url TEXT NOT NULL,
    scheduled_start_at TIMESTAMPTZ,
    actual_start_at TIMESTAMPTZ NOT NULL,
    actual_end_at TIMESTAMPTZ NOT NULL,
    duration_seconds BIGINT NOT NULL CHECK (duration_seconds >= 0),
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT streams_actual_time_order CHECK (actual_end_at >= actual_start_at)
);

-- +goose Down
DROP TABLE IF EXISTS stream.streams;
DROP SCHEMA IF EXISTS stream;
