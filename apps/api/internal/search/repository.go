package search

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"

	"github.com/jackc/pgx/v5/pgxpool"
)

var (
	ErrStreamNotFound = errors.New("stream not found")
	ErrInvalidCursor  = errors.New("invalid cursor")
)

type Item struct {
	Type                  string  `json:"type"`
	ID                    string  `json:"id"`
	OffsetMilliseconds    int64   `json:"offsetMilliseconds"`
	EndOffsetMilliseconds *int64  `json:"endOffsetMilliseconds"`
	Text                  string  `json:"text"`
	Speaker               *string `json:"speaker"`
	LanguageCode          *string `json:"languageCode"`
}

type Page struct {
	Items      []Item  `json:"items"`
	NextCursor *string `json:"nextCursor"`
	HasMore    bool    `json:"hasMore"`
}

type cursor struct {
	Offset int64  `json:"offset"`
	Type   string `json:"type"`
	ID     string `json:"id"`
}

type Repository struct{ db *pgxpool.Pool }

func NewRepository(db *pgxpool.Pool) *Repository { return &Repository{db: db} }

func (r *Repository) Search(
	ctx context.Context,
	streamID string,
	query string,
	limit int,
	encodedCursor string,
) (Page, error) {
	var exists bool
	if err := r.db.QueryRow(
		ctx,
		`SELECT EXISTS(SELECT 1 FROM stream.streams WHERE id=$1)`,
		streamID,
	).Scan(&exists); err != nil {
		return Page{}, err
	}
	if !exists {
		return Page{}, ErrStreamNotFound
	}

	var after cursor
	if encodedCursor != "" {
		decoded, err := base64.RawURLEncoding.DecodeString(encodedCursor)
		if err != nil || json.Unmarshal(decoded, &after) != nil || after.ID == "" ||
			(after.Type != "chat" && after.Type != "transcript") {
			return Page{}, ErrInvalidCursor
		}
	}
	pattern := "%" + query + "%"
	rows, err := r.db.Query(ctx, `
		WITH results AS (
			SELECT m.id::text AS id, 'chat'::text AS type,
			       m.elapsed_milliseconds::bigint AS offset_ms,
			       NULL::bigint AS end_offset_ms,
			       m.message_text AS text, m.author_name AS speaker,
			       NULL::text AS language_code
			FROM chat.chat_messages m
			WHERE m.stream_id=$1 AND m.message_text ILIKE $2
			UNION ALL
			SELECT s.id::text, 'transcript'::text,
			       s.start_offset_milliseconds::bigint,
			       s.end_offset_milliseconds::bigint,
			       s.text, NULL::text, t.language_code
			FROM transcript.transcript_segments s
			JOIN transcript.transcript_tracks t ON t.id=s.track_id
			WHERE s.stream_id=$1 AND s.text ILIKE $2
		)
		SELECT id,type,offset_ms,end_offset_ms,text,speaker,language_code
		FROM results
		WHERE $3='' OR (offset_ms,type,id) > ($4,$5,$6)
		ORDER BY offset_ms,type,id
		LIMIT $7
	`, streamID, pattern, encodedCursor, after.Offset, after.Type, after.ID, limit+1)
	if err != nil {
		return Page{}, err
	}
	defer rows.Close()

	items := make([]Item, 0, limit+1)
	for rows.Next() {
		var item Item
		if err := rows.Scan(
			&item.ID,
			&item.Type,
			&item.OffsetMilliseconds,
			&item.EndOffsetMilliseconds,
			&item.Text,
			&item.Speaker,
			&item.LanguageCode,
		); err != nil {
			return Page{}, err
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return Page{}, err
	}
	page := Page{Items: items, HasMore: len(items) > limit}
	if page.HasMore {
		last := items[limit-1]
		page.Items = items[:limit]
		value, _ := json.Marshal(cursor{
			Offset: last.OffsetMilliseconds,
			Type:   last.Type,
			ID:     last.ID,
		})
		next := base64.RawURLEncoding.EncodeToString(value)
		page.NextCursor = &next
	}
	return page, nil
}
