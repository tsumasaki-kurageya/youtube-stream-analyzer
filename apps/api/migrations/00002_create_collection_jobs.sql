-- +goose Up
CREATE SCHEMA IF NOT EXISTS collection;

CREATE TABLE collection.collection_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    stream_id uuid NOT NULL REFERENCES stream.streams(id) ON DELETE CASCADE,
    kind text NOT NULL DEFAULT 'chat' CHECK (kind = 'chat'),
    status text NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    attempt integer NOT NULL DEFAULT 1 CHECK (attempt > 0),
    retry_of_job_id uuid NULL REFERENCES collection.collection_jobs(id),
    progress_count bigint NOT NULL DEFAULT 0 CHECK (progress_count >= 0),
    error_code text NULL,
    error_message text NULL,
    worker_id text NULL,
    lease_expires_at timestamptz NULL,
    heartbeat_at timestamptz NULL,
    started_at timestamptz NULL,
    finished_at timestamptz NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX collection_jobs_active_stream_kind_uidx
    ON collection.collection_jobs(stream_id, kind)
    WHERE status IN ('queued', 'running');
CREATE INDEX collection_jobs_claim_idx
    ON collection.collection_jobs(status, created_at)
    WHERE status = 'queued';
CREATE INDEX collection_jobs_stream_created_idx
    ON collection.collection_jobs(stream_id, created_at DESC);

CREATE TABLE collection.collection_steps (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id uuid NOT NULL REFERENCES collection.collection_jobs(id) ON DELETE CASCADE,
    name text NOT NULL,
    status text NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    progress_count bigint NOT NULL DEFAULT 0 CHECK (progress_count >= 0),
    error_code text NULL,
    error_message text NULL,
    started_at timestamptz NULL,
    finished_at timestamptz NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(job_id, name)
);

-- +goose Down
DROP SCHEMA IF EXISTS collection CASCADE;
