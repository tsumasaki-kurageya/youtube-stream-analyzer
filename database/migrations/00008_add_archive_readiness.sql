-- +goose Up
ALTER TABLE reservation.reservations
    ADD COLUMN archive_wait_started_at timestamptz NULL,
    ADD COLUMN archive_ready_at timestamptz NULL,
    ADD COLUMN chat_replay_ready_at timestamptz NULL,
    ADD COLUMN ready_for_collection_at timestamptz NULL;

UPDATE reservation.reservations
SET archive_wait_started_at = COALESCE(actual_end_at, updated_at)
WHERE state = 'waiting_for_archive';

CREATE INDEX reservations_ready_for_collection_idx
    ON reservation.reservations(ready_for_collection_at, created_at)
    WHERE state = 'waiting_for_archive'
      AND ready_for_collection_at IS NOT NULL
      AND collection_job_id IS NULL;

-- +goose Down
DROP INDEX IF EXISTS reservation.reservations_ready_for_collection_idx;
ALTER TABLE reservation.reservations
    DROP COLUMN IF EXISTS ready_for_collection_at,
    DROP COLUMN IF EXISTS chat_replay_ready_at,
    DROP COLUMN IF EXISTS archive_ready_at,
    DROP COLUMN IF EXISTS archive_wait_started_at;
