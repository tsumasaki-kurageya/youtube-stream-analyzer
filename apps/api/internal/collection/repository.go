package collection

import (
	"context"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

var (
	ErrNotFound = errors.New("collection job not found")
	ErrConflict = errors.New("active collection job already exists")
	ErrNotRetryable = errors.New("collection job is not retryable")
)

type Job struct {
	ID            string
	StreamID      string
	Kind          string
	Status        string
	Attempt       int
	RetryOfJobID  *string
	ProgressCount int64
	ErrorCode     *string
	ErrorMessage  *string
	StartedAt     *time.Time
	FinishedAt    *time.Time
	CreatedAt     time.Time
	UpdatedAt     time.Time
}

type Step struct {
	ID            string
	JobID         string
	Name          string
	Status        string
	ProgressCount int64
	ErrorCode     *string
	ErrorMessage  *string
	StartedAt     *time.Time
	FinishedAt    *time.Time
}

type JobWithSteps struct {
	Job
	Steps []Step
}

type Repository struct{ db *pgxpool.Pool }

func NewRepository(db *pgxpool.Pool) *Repository { return &Repository{db: db} }

func (r *Repository) Create(ctx context.Context, streamID string) (JobWithSteps, error) {
	tx, err := r.db.Begin(ctx)
	if err != nil { return JobWithSteps{}, err }
	defer tx.Rollback(ctx)

	var exists bool
	if err := tx.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM stream.streams WHERE id=$1)`, streamID).Scan(&exists); err != nil { return JobWithSteps{}, err }
	if !exists { return JobWithSteps{}, ErrNotFound }

	job, err := insertJob(ctx, tx, streamID, 1, nil)
	if err != nil {
		if isUniqueViolation(err) { return JobWithSteps{}, ErrConflict }
		return JobWithSteps{}, err
	}
	step, err := insertStep(ctx, tx, job.ID)
	if err != nil { return JobWithSteps{}, err }
	if err := tx.Commit(ctx); err != nil { return JobWithSteps{}, err }
	return JobWithSteps{Job: job, Steps: []Step{step}}, nil
}

func (r *Repository) Latest(ctx context.Context, streamID string) (JobWithSteps, error) {
	job, err := scanJob(r.db.QueryRow(ctx, `SELECT id,stream_id,kind,status,attempt,retry_of_job_id,progress_count,error_code,error_message,started_at,finished_at,created_at,updated_at FROM collection.collection_jobs WHERE stream_id=$1 AND kind='chat' ORDER BY created_at DESC LIMIT 1`, streamID))
	if errors.Is(err, pgx.ErrNoRows) { return JobWithSteps{}, ErrNotFound }
	if err != nil { return JobWithSteps{}, err }
	steps, err := r.steps(ctx, job.ID)
	if err != nil { return JobWithSteps{}, err }
	return JobWithSteps{Job: job, Steps: steps}, nil
}

func (r *Repository) Retry(ctx context.Context, jobID string) (JobWithSteps, error) {
	tx, err := r.db.Begin(ctx)
	if err != nil { return JobWithSteps{}, err }
	defer tx.Rollback(ctx)
	original, err := scanJob(tx.QueryRow(ctx, `SELECT id,stream_id,kind,status,attempt,retry_of_job_id,progress_count,error_code,error_message,started_at,finished_at,created_at,updated_at FROM collection.collection_jobs WHERE id=$1 FOR UPDATE`, jobID))
	if errors.Is(err, pgx.ErrNoRows) { return JobWithSteps{}, ErrNotFound }
	if err != nil { return JobWithSteps{}, err }
	if original.Status != "failed" { return JobWithSteps{}, ErrNotRetryable }
	job, err := insertJob(ctx, tx, original.StreamID, original.Attempt+1, &original.ID)
	if err != nil {
		if isUniqueViolation(err) { return JobWithSteps{}, ErrConflict }
		return JobWithSteps{}, err
	}
	step, err := insertStep(ctx, tx, job.ID)
	if err != nil { return JobWithSteps{}, err }
	if err := tx.Commit(ctx); err != nil { return JobWithSteps{}, err }
	return JobWithSteps{Job: job, Steps: []Step{step}}, nil
}

func insertJob(ctx context.Context, tx pgx.Tx, streamID string, attempt int, retryOf *string) (Job, error) {
	return scanJob(tx.QueryRow(ctx, `INSERT INTO collection.collection_jobs(stream_id,status,attempt,retry_of_job_id) VALUES($1,'queued',$2,$3) RETURNING id,stream_id,kind,status,attempt,retry_of_job_id,progress_count,error_code,error_message,started_at,finished_at,created_at,updated_at`, streamID, attempt, retryOf))
}

func insertStep(ctx context.Context, tx pgx.Tx, jobID string) (Step, error) {
	var step Step
	err := tx.QueryRow(ctx, `INSERT INTO collection.collection_steps(job_id,name,status) VALUES($1,'chat_replay','queued') RETURNING id,job_id,name,status,progress_count,error_code,error_message,started_at,finished_at`, jobID).Scan(&step.ID,&step.JobID,&step.Name,&step.Status,&step.ProgressCount,&step.ErrorCode,&step.ErrorMessage,&step.StartedAt,&step.FinishedAt)
	return step, err
}

func (r *Repository) steps(ctx context.Context, jobID string) ([]Step, error) {
	rows, err := r.db.Query(ctx, `SELECT id,job_id,name,status,progress_count,error_code,error_message,started_at,finished_at FROM collection.collection_steps WHERE job_id=$1 ORDER BY created_at`, jobID)
	if err != nil { return nil, err }
	defer rows.Close()
	result := []Step{}
	for rows.Next() {
		var s Step
		if err := rows.Scan(&s.ID,&s.JobID,&s.Name,&s.Status,&s.ProgressCount,&s.ErrorCode,&s.ErrorMessage,&s.StartedAt,&s.FinishedAt); err != nil { return nil, err }
		result = append(result, s)
	}
	return result, rows.Err()
}

type rowScanner interface { Scan(...any) error }
func scanJob(row rowScanner) (Job, error) {
	var j Job
	err := row.Scan(&j.ID,&j.StreamID,&j.Kind,&j.Status,&j.Attempt,&j.RetryOfJobID,&j.ProgressCount,&j.ErrorCode,&j.ErrorMessage,&j.StartedAt,&j.FinishedAt,&j.CreatedAt,&j.UpdatedAt)
	return j, err
}

func isUniqueViolation(err error) bool { return err != nil && (contains(err.Error(), "23505") || contains(err.Error(), "duplicate key")) }
func contains(value, part string) bool {
	for i := 0; i+len(part) <= len(value); i++ { if value[i:i+len(part)] == part { return true } }
	return false
}
