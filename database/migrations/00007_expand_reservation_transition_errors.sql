-- +goose Up
ALTER TABLE reservation.reservation_transitions
    ADD COLUMN error_code text NULL,
    ADD COLUMN error_message text NULL;

-- +goose Down
ALTER TABLE reservation.reservation_transitions
    DROP COLUMN error_message,
    DROP COLUMN error_code;
