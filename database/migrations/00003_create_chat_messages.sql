-- +goose Up
CREATE SCHEMA IF NOT EXISTS chat;

CREATE TABLE chat.chat_messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    stream_id uuid NOT NULL REFERENCES stream.streams(id) ON DELETE CASCADE,
    collection_job_id uuid NOT NULL REFERENCES collection.collection_jobs(id) ON DELETE CASCADE,
    external_message_id text NOT NULL,
    author_external_id text,
    author_name text NOT NULL,
    message_text text NOT NULL,
    published_at timestamptz NOT NULL,
    elapsed_milliseconds bigint NOT NULL CHECK (elapsed_milliseconds >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chat_messages_stream_external_uidx UNIQUE (stream_id, external_message_id)
);

CREATE INDEX chat_messages_stream_elapsed_idx
    ON chat.chat_messages(stream_id, elapsed_milliseconds, published_at, external_message_id);
CREATE INDEX chat_messages_stream_published_idx
    ON chat.chat_messages(stream_id, published_at, external_message_id);
CREATE INDEX chat_messages_job_idx
    ON chat.chat_messages(collection_job_id);

-- +goose Down
DROP TABLE IF EXISTS chat.chat_messages;
DROP SCHEMA IF EXISTS chat;
