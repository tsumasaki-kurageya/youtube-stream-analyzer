-- +goose Up
DROP INDEX collection.collection_jobs_active_stream_kind_uidx;

ALTER TABLE collection.collection_jobs
    DROP CONSTRAINT collection_jobs_kind_check,
    DROP CONSTRAINT collection_jobs_status_check;

ALTER TABLE collection.collection_jobs
    ALTER COLUMN kind SET DEFAULT 'full',
    ADD COLUMN requested_steps text[] NOT NULL DEFAULT ARRAY['chat_replay']::text[];

ALTER TABLE collection.collection_jobs
    ADD CONSTRAINT collection_jobs_kind_check CHECK (kind IN ('chat','full')),
    ADD CONSTRAINT collection_jobs_status_check CHECK (
        status IN ('queued','running','succeeded','partial','failed','cancelled')
    );

CREATE UNIQUE INDEX collection_jobs_active_stream_uidx
    ON collection.collection_jobs(stream_id)
    WHERE status IN ('queued','running');

ALTER TABLE collection.collection_steps
    DROP CONSTRAINT collection_steps_status_check;

ALTER TABLE collection.collection_steps
    ADD COLUMN attempt integer NOT NULL DEFAULT 1 CHECK (attempt > 0),
    ADD COLUMN worker_id text,
    ADD COLUMN lease_expires_at timestamptz,
    ADD COLUMN heartbeat_at timestamptz,
    ADD COLUMN retryable boolean,
    ADD CONSTRAINT collection_steps_status_check CHECK (
        status IN ('queued','running','succeeded','no_data','failed','cancelled')
    );

CREATE TABLE collection.collection_step_attempts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    step_id uuid NOT NULL REFERENCES collection.collection_steps(id) ON DELETE CASCADE,
    attempt integer NOT NULL CHECK (attempt > 0),
    status text NOT NULL CHECK (
        status IN ('queued','running','succeeded','no_data','failed','cancelled')
    ),
    worker_id text,
    progress_count bigint NOT NULL DEFAULT 0 CHECK (progress_count >= 0),
    error_code text,
    error_message text,
    retryable boolean,
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(step_id, attempt)
);

INSERT INTO collection.collection_step_attempts(
    step_id, attempt, status, progress_count, error_code, error_message,
    started_at, finished_at
)
SELECT id, 1, status, progress_count, error_code, error_message,
       started_at, finished_at
FROM collection.collection_steps;

CREATE INDEX collection_steps_claim_idx
    ON collection.collection_steps(status, created_at, id)
    WHERE status='queued';
CREATE INDEX collection_steps_lease_idx
    ON collection.collection_steps(lease_expires_at)
    WHERE status='running';
CREATE INDEX collection_step_attempts_step_idx
    ON collection.collection_step_attempts(step_id, attempt DESC);

-- +goose Down
DROP INDEX IF EXISTS collection.collection_step_attempts_step_idx;
DROP INDEX IF EXISTS collection.collection_steps_lease_idx;
DROP INDEX IF EXISTS collection.collection_steps_claim_idx;
DROP TABLE IF EXISTS collection.collection_step_attempts;

ALTER TABLE collection.collection_steps
    DROP CONSTRAINT collection_steps_status_check;

UPDATE collection.collection_steps
SET status = CASE
    WHEN status = 'no_data' THEN 'succeeded'
    WHEN status = 'cancelled' THEN 'failed'
    ELSE status
END;

ALTER TABLE collection.collection_steps
    DROP COLUMN retryable,
    DROP COLUMN heartbeat_at,
    DROP COLUMN lease_expires_at,
    DROP COLUMN worker_id,
    DROP COLUMN attempt,
    ADD CONSTRAINT collection_steps_status_check CHECK (
        status IN ('queued','running','succeeded','failed')
    );

DROP INDEX collection.collection_jobs_active_stream_uidx;

ALTER TABLE collection.collection_jobs
    DROP CONSTRAINT collection_jobs_status_check,
    DROP CONSTRAINT collection_jobs_kind_check;

UPDATE collection.collection_jobs
SET kind = 'chat',
    status = CASE
        WHEN status = 'partial' THEN 'failed'
        WHEN status = 'cancelled' THEN 'failed'
        ELSE status
    END;

ALTER TABLE collection.collection_jobs
    DROP COLUMN requested_steps,
    ALTER COLUMN kind SET DEFAULT 'chat',
    ADD CONSTRAINT collection_jobs_kind_check CHECK (kind='chat'),
    ADD CONSTRAINT collection_jobs_status_check CHECK (
        status IN ('queued','running','succeeded','failed')
    );

CREATE UNIQUE INDEX collection_jobs_active_stream_kind_uidx
    ON collection.collection_jobs(stream_id, kind)
    WHERE status IN ('queued','running');
