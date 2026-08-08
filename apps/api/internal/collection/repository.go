package collection

import (
	"context"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

var (
	ErrNotFound     = errors.New("collection job not found")
	ErrConflict     = errors.New("active collection job already exists")
	ErrNotRetryable = errors.New("collection step is not retryable")
)

var fullSteps = []string{"metadata", "chat_replay", "transcript"}

type Job struct {
	ID             string
	StreamID       string
	Kind           string
	Status         string
	Attempt        int
	RetryOfJobID   *string
	RequestedSteps []string
	ProgressCount  int64
	ErrorCode      *string
	ErrorMessage   *string
	StartedAt      *time.Time
	FinishedAt     *time.Time
	CreatedAt      time.Time
	UpdatedAt      time.Time
}

type Step struct {
	ID             string
	JobID          string
	Name           string
	Status         string
	Attempt        int
	ProgressCount  int64
	ErrorCode      *string
	ErrorMessage   *string
	Retryable      *bool
	HeartbeatAt    *time.Time
	LeaseExpiresAt *time.Time
	StartedAt      *time.Time
	FinishedAt     *time.Time
}

type JobWithSteps struct {
	Job
	Steps []Step
}

type Repository struct{ db *pgxpool.Pool }

func NewRepository(db *pgxpool.Pool) *Repository { return &Repository{db: db} }

func (r *Repository) Create(ctx context.Context, streamID string) (JobWithSteps, error) {
	return r.create(ctx, streamID, "chat", []string{"chat_replay"})
}

func (r *Repository) CreateFull(ctx context.Context, streamID string) (JobWithSteps, error) {
	return r.create(ctx, streamID, "full", fullSteps)
}

func (r *Repository) create(
	ctx context.Context,
	streamID string,
	kind string,
	stepNames []string,
) (JobWithSteps, error) {
	tx, err := r.db.Begin(ctx)
	if err != nil {
		return JobWithSteps{}, err
	}
	defer tx.Rollback(ctx)

	var exists bool
	if err := tx.QueryRow(
		ctx,
		`SELECT EXISTS(SELECT 1 FROM stream.streams WHERE id=$1)`,
		streamID,
	).Scan(&exists); err != nil {
		return JobWithSteps{}, err
	}
	if !exists {
		return JobWithSteps{}, ErrNotFound
	}

	job, err := insertJob(ctx, tx, streamID, kind, stepNames)
	if err != nil {
		if isUniqueViolation(err) {
			return JobWithSteps{}, ErrConflict
		}
		return JobWithSteps{}, err
	}
	steps := make([]Step, 0, len(stepNames))
	for _, name := range stepNames {
		step, err := insertStep(ctx, tx, job.ID, name)
		if err != nil {
			return JobWithSteps{}, err
		}
		steps = append(steps, step)
	}
	if err := tx.Commit(ctx); err != nil {
		return JobWithSteps{}, err
	}
	return JobWithSteps{Job: job, Steps: steps}, nil
}

func (r *Repository) Latest(ctx context.Context, streamID string) (JobWithSteps, error) {
	job, err := scanJob(r.db.QueryRow(ctx, `
		SELECT id,stream_id,kind,status,attempt,retry_of_job_id,requested_steps,
		       progress_count,error_code,error_message,started_at,finished_at,
		       created_at,updated_at
		FROM collection.collection_jobs
		WHERE stream_id=$1
		ORDER BY created_at DESC LIMIT 1`, streamID))
	if errors.Is(err, pgx.ErrNoRows) {
		return JobWithSteps{}, ErrNotFound
	}
	if err != nil {
		return JobWithSteps{}, err
	}
	steps, err := r.steps(ctx, job.ID)
	if err != nil {
		return JobWithSteps{}, err
	}
	return JobWithSteps{Job: job, Steps: steps}, nil
}

func (r *Repository) Retry(ctx context.Context, jobID string) (JobWithSteps, error) {
	job, err := r.get(ctx, jobID)
	if err != nil {
		return JobWithSteps{}, err
	}
	for _, step := range job.Steps {
		if step.Status == "failed" && step.Retryable != nil && *step.Retryable {
			if _, err := r.RetryStep(ctx, jobID, step.Name); err != nil {
				return JobWithSteps{}, err
			}
		}
	}
	return r.get(ctx, jobID)
}

func (r *Repository) RetryStep(ctx context.Context, jobID, stepName string) (Step, error) {
	tx, err := r.db.Begin(ctx)
	if err != nil {
		return Step{}, err
	}
	defer tx.Rollback(ctx)

	step, err := scanStep(tx.QueryRow(ctx, `
		SELECT id,job_id,name,status,attempt,progress_count,error_code,error_message,
		       retryable,heartbeat_at,lease_expires_at,started_at,finished_at
		FROM collection.collection_steps
		WHERE job_id=$1 AND name=$2 FOR UPDATE`, jobID, stepName))
	if errors.Is(err, pgx.ErrNoRows) {
		return Step{}, ErrNotFound
	}
	if err != nil {
		return Step{}, err
	}
	if step.Status != "failed" || step.Retryable == nil || !*step.Retryable {
		return Step{}, ErrNotRetryable
	}

	step.Attempt++
	step.Status = "queued"
	step.ProgressCount = 0
	step.ErrorCode = nil
	step.ErrorMessage = nil
	step.Retryable = nil
	step.StartedAt = nil
	step.FinishedAt = nil
	if err := tx.QueryRow(ctx, `
		UPDATE collection.collection_steps
		SET status='queued',attempt=$3,progress_count=0,error_code=NULL,
		    error_message=NULL,retryable=NULL,worker_id=NULL,lease_expires_at=NULL,
		    heartbeat_at=NULL,started_at=NULL,finished_at=NULL,updated_at=now()
		WHERE job_id=$1 AND name=$2
		RETURNING id,job_id,name,status,attempt,progress_count,error_code,error_message,
		          retryable,heartbeat_at,lease_expires_at,started_at,finished_at`, jobID, stepName, step.Attempt).Scan(
		&step.ID,
		&step.JobID,
		&step.Name,
		&step.Status,
		&step.Attempt,
		&step.ProgressCount,
		&step.ErrorCode,
		&step.ErrorMessage,
		&step.Retryable,
		&step.HeartbeatAt,
		&step.LeaseExpiresAt,
		&step.StartedAt,
		&step.FinishedAt,
	); err != nil {
		return Step{}, err
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO collection.collection_step_attempts(step_id,attempt,status)
		VALUES($1,$2,'queued')`, step.ID, step.Attempt); err != nil {
		return Step{}, err
	}
	if _, err := tx.Exec(ctx, `
		UPDATE collection.collection_jobs
		SET status='queued',finished_at=NULL,error_code=NULL,error_message=NULL,
		    updated_at=now()
		WHERE id=$1`, jobID); err != nil {
		return Step{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return Step{}, err
	}
	return step, nil
}

func (r *Repository) get(ctx context.Context, jobID string) (JobWithSteps, error) {
	job, err := scanJob(r.db.QueryRow(ctx, `
		SELECT id,stream_id,kind,status,attempt,retry_of_job_id,requested_steps,
		       progress_count,error_code,error_message,started_at,finished_at,
		       created_at,updated_at
		FROM collection.collection_jobs WHERE id=$1`, jobID))
	if errors.Is(err, pgx.ErrNoRows) {
		return JobWithSteps{}, ErrNotFound
	}
	if err != nil {
		return JobWithSteps{}, err
	}
	steps, err := r.steps(ctx, jobID)
	if err != nil {
		return JobWithSteps{}, err
	}
	return JobWithSteps{Job: job, Steps: steps}, nil
}

func insertJob(
	ctx context.Context,
	tx pgx.Tx,
	streamID string,
	kind string,
	steps []string,
) (Job, error) {
	return scanJob(tx.QueryRow(ctx, `
		INSERT INTO collection.collection_jobs(
			stream_id,kind,status,requested_steps
		) VALUES($1,$2,'queued',$3)
		RETURNING id,stream_id,kind,status,attempt,retry_of_job_id,requested_steps,
		          progress_count,error_code,error_message,started_at,finished_at,
		          created_at,updated_at`, streamID, kind, steps))
}

func insertStep(ctx context.Context, tx pgx.Tx, jobID, name string) (Step, error) {
	step, err := scanStep(tx.QueryRow(ctx, `
		INSERT INTO collection.collection_steps(job_id,name,status)
		VALUES($1,$2,'queued')
		RETURNING id,job_id,name,status,attempt,progress_count,error_code,error_message,
		          retryable,heartbeat_at,lease_expires_at,started_at,finished_at`, jobID, name))
	if err != nil {
		return Step{}, err
	}
	_, err = tx.Exec(ctx, `
		INSERT INTO collection.collection_step_attempts(step_id,attempt,status)
		VALUES($1,1,'queued')`, step.ID)
	return step, err
}

func (r *Repository) steps(ctx context.Context, jobID string) ([]Step, error) {
	rows, err := r.db.Query(ctx, `
		SELECT id,job_id,name,status,attempt,progress_count,error_code,error_message,
		       retryable,heartbeat_at,lease_expires_at,started_at,finished_at
		FROM collection.collection_steps WHERE job_id=$1
		ORDER BY created_at`, jobID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	result := []Step{}
	for rows.Next() {
		step, err := scanStep(rows)
		if err != nil {
			return nil, err
		}
		result = append(result, step)
	}
	return result, rows.Err()
}

type rowScanner interface{ Scan(...any) error }

func scanJob(row rowScanner) (Job, error) {
	var job Job
	err := row.Scan(
		&job.ID,
		&job.StreamID,
		&job.Kind,
		&job.Status,
		&job.Attempt,
		&job.RetryOfJobID,
		&job.RequestedSteps,
		&job.ProgressCount,
		&job.ErrorCode,
		&job.ErrorMessage,
		&job.StartedAt,
		&job.FinishedAt,
		&job.CreatedAt,
		&job.UpdatedAt,
	)
	return job, err
}

func scanStep(row rowScanner) (Step, error) {
	var step Step
	err := row.Scan(
		&step.ID,
		&step.JobID,
		&step.Name,
		&step.Status,
		&step.Attempt,
		&step.ProgressCount,
		&step.ErrorCode,
		&step.ErrorMessage,
		&step.Retryable,
		&step.HeartbeatAt,
		&step.LeaseExpiresAt,
		&step.StartedAt,
		&step.FinishedAt,
	)
	return step, err
}

func isUniqueViolation(err error) bool {
	var pgErr *pgconn.PgError
	return errors.As(err, &pgErr) && pgErr.Code == "23505"
}
