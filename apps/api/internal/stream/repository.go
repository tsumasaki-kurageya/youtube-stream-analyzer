package stream

import (
	"context"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Stream struct {
	ID               string
	YouTubeVideoID   string
	SourceURL        string
	Title            string
	ChannelID        string
	ChannelTitle     string
	ThumbnailURL     string
	ScheduledStartAt *time.Time
	ActualStartAt    time.Time
	ActualEndAt      time.Time
	DurationSeconds  int64
	PublishedAt      *time.Time
	CreatedAt        time.Time
	UpdatedAt        time.Time
}

type Repository struct{ db *pgxpool.Pool }

func NewRepository(db *pgxpool.Pool) *Repository { return &Repository{db: db} }

func (r *Repository) Insert(ctx context.Context, value Stream) (Stream, error) {
	row := r.db.QueryRow(ctx, `
		INSERT INTO stream.streams (
			youtube_video_id, source_url, title, channel_id, channel_title,
			thumbnail_url, scheduled_start_at, actual_start_at, actual_end_at,
			duration_seconds, published_at
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
		RETURNING id, youtube_video_id, source_url, title, channel_id, channel_title,
			thumbnail_url, scheduled_start_at, actual_start_at, actual_end_at,
			duration_seconds, published_at, created_at, updated_at`,
		value.YouTubeVideoID, value.SourceURL, value.Title, value.ChannelID,
		value.ChannelTitle, value.ThumbnailURL, value.ScheduledStartAt,
		value.ActualStartAt, value.ActualEndAt, value.DurationSeconds, value.PublishedAt,
	)
	return scanStream(row)
}

func (r *Repository) Get(ctx context.Context, id string) (Stream, error) {
	row := r.db.QueryRow(ctx, `SELECT id, youtube_video_id, source_url, title, channel_id,
		channel_title, thumbnail_url, scheduled_start_at, actual_start_at, actual_end_at,
		duration_seconds, published_at, created_at, updated_at
		FROM stream.streams WHERE id = $1`, id)
	return scanStream(row)
}

func (r *Repository) List(ctx context.Context) ([]Stream, error) {
	rows, err := r.db.Query(ctx, `SELECT id, youtube_video_id, source_url, title, channel_id,
		channel_title, thumbnail_url, scheduled_start_at, actual_start_at, actual_end_at,
		duration_seconds, published_at, created_at, updated_at
		FROM stream.streams ORDER BY created_at DESC`)
	if err != nil { return nil, err }
	defer rows.Close()

	items := make([]Stream, 0)
	for rows.Next() {
		item, err := scanStream(rows)
		if err != nil { return nil, err }
		items = append(items, item)
	}
	return items, rows.Err()
}

func IsNotFound(err error) bool { return errors.Is(err, pgx.ErrNoRows) }

type scanner interface{ Scan(...any) error }

func scanStream(row scanner) (Stream, error) {
	var value Stream
	err := row.Scan(&value.ID, &value.YouTubeVideoID, &value.SourceURL, &value.Title,
		&value.ChannelID, &value.ChannelTitle, &value.ThumbnailURL, &value.ScheduledStartAt,
		&value.ActualStartAt, &value.ActualEndAt, &value.DurationSeconds,
		&value.PublishedAt, &value.CreatedAt, &value.UpdatedAt)
	return value, err
}
