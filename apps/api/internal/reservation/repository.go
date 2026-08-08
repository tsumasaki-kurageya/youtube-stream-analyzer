package reservation

import (
	"context"
	"errors"
	"strconv"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

var (
	ErrNotFound       = errors.New("reservation not found")
	ErrAlreadyActive  = errors.New("reservation already active")
	ErrNotCancellable = errors.New("reservation not cancellable")
)

type Reservation struct {
	ID                     string
	YouTubeVideoID         string
	SourceURL               string
	State                   string
	ScheduledStartAt        *time.Time
	ActualStartAt           *time.Time
	ActualEndAt             *time.Time
	NextCheckAt             time.Time
	LastCheckedAt           *time.Time
	MonitorAttempt          int
	LastErrorCode           *string
	LastErrorMessage        *string
	LastErrorRetryable      *bool
	StreamID                *string
	CollectionJobID         *string
	CollectionStatus        *string
	CollectionErrorCode     *string
	CollectionErrorMessage  *string
	CancelledAt             *time.Time
	CompletedAt             *time.Time
	FailedAt                *time.Time
	CreatedAt               time.Time
	UpdatedAt               time.Time
}

type CreateInput struct {
	YouTubeVideoID   string
	SourceURL        string
	State            string
	ScheduledStartAt *time.Time
	ActualStartAt    *time.Time
	ActualEndAt      *time.Time
	NextCheckAt      time.Time
}

type Repository struct{ db *pgxpool.Pool }

func NewRepository(db *pgxpool.Pool) *Repository { return &Repository{db: db} }

const selectReservation = `
SELECT r.id::text,r.youtube_video_id,r.source_url,r.state,
       r.scheduled_start_at,r.actual_start_at,r.actual_end_at,r.next_check_at,
       r.last_checked_at,r.monitor_attempt,r.last_error_code,r.last_error_message,
       r.last_error_retryable,r.stream_id::text,r.collection_job_id::text,
       j.status,j.error_code,j.error_message,
       r.cancelled_at,r.completed_at,r.failed_at,r.created_at,r.updated_at
FROM reservation.reservations r
LEFT JOIN collection.collection_jobs j ON j.id=r.collection_job_id`

func scan(row pgx.Row) (Reservation, error) {
	var value Reservation
	err := row.Scan(
		&value.ID,
		&value.YouTubeVideoID,
		&value.SourceURL,
		&value.State,
		&value.ScheduledStartAt,
		&value.ActualStartAt,
		&value.ActualEndAt,
		&value.NextCheckAt,
		&value.LastCheckedAt,
		&value.MonitorAttempt,
		&value.LastErrorCode,
		&value.LastErrorMessage,
		&value.LastErrorRetryable,
		&value.StreamID,
		&value.CollectionJobID,
		&value.CollectionStatus,
		&value.CollectionErrorCode,
		&value.CollectionErrorMessage,
		&value.CancelledAt,
		&value.CompletedAt,
		&value.FailedAt,
		&value.CreatedAt,
		&value.UpdatedAt,
	)
	return value, err
}

func (r *Repository) Create(ctx context.Context, input CreateInput) (Reservation, error) {
	tx, err := r.db.Begin(ctx)
	if err != nil {
		return Reservation{}, err
	}
	defer tx.Rollback(ctx)

	var id string
	err = tx.QueryRow(ctx, `
		INSERT INTO reservation.reservations(
			youtube_video_id,source_url,state,scheduled_start_at,actual_start_at,
			actual_end_at,next_check_at
		) VALUES($1,$2,$3,$4,$5,$6,$7)
		RETURNING id::text
	`, input.YouTubeVideoID, input.SourceURL, input.State, input.ScheduledStartAt,
		input.ActualStartAt, input.ActualEndAt, input.NextCheckAt).Scan(&id)
	if err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "23505" {
			return Reservation{}, ErrAlreadyActive
		}
		return Reservation{}, err
	}
	if _, err = tx.Exec(ctx, `
		INSERT INTO reservation.reservation_transitions(
			reservation_id,from_state,to_state,reason_code
		) VALUES($1,NULL,$2,'reservation_created')
	`, id, input.State); err != nil {
		return Reservation{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return Reservation{}, err
	}
	return r.Get(ctx, id)
}

func (r *Repository) Get(ctx context.Context, id string) (Reservation, error) {
	value, err := scan(r.db.QueryRow(ctx, selectReservation+` WHERE r.id=$1`, id))
	if errors.Is(err, pgx.ErrNoRows) {
		return Reservation{}, ErrNotFound
	}
	return value, err
}

func (r *Repository) List(ctx context.Context, state string, limit, offset int) ([]Reservation, int, error) {
	where := ""
	args := make([]any, 0, 3)
	if state != "" {
		where = " WHERE r.state=$1"
		args = append(args, state)
	}
	var total int
	if err := r.db.QueryRow(ctx, `SELECT count(*) FROM reservation.reservations r`+where, args...).Scan(&total); err != nil {
		return nil, 0, err
	}
	args = append(args, limit, offset)
	limitPos := strconv.Itoa(len(args) - 1)
	offsetPos := strconv.Itoa(len(args))
	rows, err := r.db.Query(ctx,
		selectReservation+where+` ORDER BY r.created_at DESC,r.id DESC LIMIT $`+limitPos+` OFFSET $`+offsetPos,
		args...,
	)
	if err != nil {
		return nil, 0, err
	}
	defer rows.Close()
	items := make([]Reservation, 0, limit)
	for rows.Next() {
		value, err := scan(rows)
		if err != nil {
			return nil, 0, err
		}
		items = append(items, value)
	}
	return items, total, rows.Err()
}

func (r *Repository) Cancel(ctx context.Context, id string) (Reservation, error) {
	tx, err := r.db.Begin(ctx)
	if err != nil {
		return Reservation{}, err
	}
	defer tx.Rollback(ctx)

	var fromState string
	err = tx.QueryRow(ctx, `
		WITH current AS (
			SELECT id,state FROM reservation.reservations
			WHERE id=$1 AND state IN ('scheduled','monitoring','live','waiting_for_archive')
			FOR UPDATE
		), updated AS (
			UPDATE reservation.reservations r
			SET state='cancelled',cancelled_at=now(),worker_id=NULL,lease_expires_at=NULL,
			    heartbeat_at=NULL,revision=revision+1,updated_at=now()
			FROM current c WHERE r.id=c.id
			RETURNING c.state
		)
		SELECT state FROM updated
	`, id).Scan(&fromState)
	if errors.Is(err, pgx.ErrNoRows) {
		var exists bool
		if lookupErr := tx.QueryRow(ctx,
			`SELECT EXISTS(SELECT 1 FROM reservation.reservations WHERE id=$1)`, id,
		).Scan(&exists); lookupErr != nil {
			return Reservation{}, lookupErr
		}
		if !exists {
			return Reservation{}, ErrNotFound
		}
		return Reservation{}, ErrNotCancellable
	}
	if err != nil {
		return Reservation{}, err
	}
	if _, err = tx.Exec(ctx, `
		INSERT INTO reservation.reservation_transitions(
			reservation_id,from_state,to_state,reason_code
		) VALUES($1,$2,'cancelled','user_cancelled')
	`, id, fromState); err != nil {
		return Reservation{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return Reservation{}, err
	}
	return r.Get(ctx, id)
}
