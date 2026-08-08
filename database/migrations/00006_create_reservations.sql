-- +goose Up
CREATE SCHEMA IF NOT EXISTS reservation;

CREATE TABLE reservation.reservations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    youtube_video_id text NOT NULL CHECK (length(youtube_video_id) = 11),
    source_url text NOT NULL,
    state text NOT NULL CHECK (state IN (
        'scheduled','monitoring','live','waiting_for_archive',
        'collecting','completed','cancelled','failed'
    )),
    scheduled_start_at timestamptz NULL,
    actual_start_at timestamptz NULL,
    actual_end_at timestamptz NULL,
    next_check_at timestamptz NOT NULL,
    last_checked_at timestamptz NULL,
    monitor_attempt integer NOT NULL DEFAULT 0 CHECK (monitor_attempt >= 0),
    last_error_code text NULL,
    last_error_message text NULL,
    last_error_retryable boolean NULL,
    stream_id uuid NULL REFERENCES stream.streams(id) ON DELETE SET NULL,
    collection_job_id uuid NULL REFERENCES collection.collection_jobs(id) ON DELETE SET NULL,
    worker_id text NULL,
    lease_expires_at timestamptz NULL,
    heartbeat_at timestamptz NULL,
    revision bigint NOT NULL DEFAULT 0 CHECK (revision >= 0),
    cancelled_at timestamptz NULL,
    completed_at timestamptz NULL,
    failed_at timestamptz NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX reservations_active_video_uidx
    ON reservation.reservations(youtube_video_id)
    WHERE state NOT IN ('completed','cancelled','failed');
CREATE UNIQUE INDEX reservations_collection_job_uidx
    ON reservation.reservations(collection_job_id)
    WHERE collection_job_id IS NOT NULL;
CREATE INDEX reservations_due_idx
    ON reservation.reservations(next_check_at, created_at)
    WHERE state IN ('scheduled','monitoring','live','waiting_for_archive','collecting');
CREATE INDEX reservations_state_created_idx
    ON reservation.reservations(state, created_at DESC, id DESC);

CREATE TABLE reservation.reservation_transitions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    reservation_id uuid NOT NULL REFERENCES reservation.reservations(id) ON DELETE CASCADE,
    from_state text NULL,
    to_state text NOT NULL,
    reason_code text NOT NULL,
    detail text NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX reservation_transitions_reservation_idx
    ON reservation.reservation_transitions(reservation_id, created_at, id);

-- +goose Down
DROP SCHEMA IF EXISTS reservation CASCADE;
