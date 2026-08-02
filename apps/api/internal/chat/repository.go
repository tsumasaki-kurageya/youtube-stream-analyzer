package chat

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

var ErrStreamNotFound = errors.New("stream not found")

type Message struct {
	ID                  string    `json:"id"`
	ExternalMessageID   string    `json:"externalMessageId"`
	AuthorExternalID    *string   `json:"authorExternalId"`
	AuthorName          string    `json:"authorName"`
	MessageText         string    `json:"messageText"`
	PublishedAt         time.Time `json:"publishedAt"`
	ElapsedMilliseconds int64     `json:"elapsedMilliseconds"`
}

type Page struct {
	Items      []Message `json:"items"`
	NextCursor *string   `json:"nextCursor"`
}

type cursor struct {
	Elapsed   int64     `json:"e"`
	Published time.Time `json:"p"`
	External  string    `json:"x"`
}

type Repository struct{ db *pgxpool.Pool }

func NewRepository(db *pgxpool.Pool) *Repository { return &Repository{db: db} }

func (r *Repository) List(ctx context.Context, streamID string, limit int, cursorValue string) (Page, error) {
	var exists bool
	if err := r.db.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM stream.streams WHERE id=$1)`, streamID).Scan(&exists); err != nil {
		return Page{}, err
	}
	if !exists {
		return Page{}, ErrStreamNotFound
	}

	query := `SELECT id,external_message_id,author_external_id,author_name,message_text,published_at,elapsed_milliseconds
		FROM chat.chat_messages WHERE stream_id=$1`
	args := []any{streamID}
	if cursorValue != "" {
		after, err := decodeCursor(cursorValue)
		if err != nil {
			return Page{}, err
		}
		query += ` AND (elapsed_milliseconds,published_at,external_message_id) > ($2,$3,$4)`
		args = append(args, after.Elapsed, after.Published, after.External)
	}
	query += fmt.Sprintf(` ORDER BY elapsed_milliseconds,published_at,external_message_id LIMIT $%d`, len(args)+1)
	args = append(args, limit+1)

	rows, err := r.db.Query(ctx, query, args...)
	if err != nil {
		return Page{}, err
	}
	defer rows.Close()

	items := make([]Message, 0, limit+1)
	for rows.Next() {
		var item Message
		if err := rows.Scan(&item.ID, &item.ExternalMessageID, &item.AuthorExternalID, &item.AuthorName, &item.MessageText, &item.PublishedAt, &item.ElapsedMilliseconds); err != nil {
			return Page{}, err
		}
		items = append(items, item)
	}
	if err := rows.Err(); err != nil {
		return Page{}, err
	}

	page := Page{Items: items}
	if len(items) > limit {
		last := items[limit-1]
		value, err := encodeCursor(cursor{Elapsed: last.ElapsedMilliseconds, Published: last.PublishedAt, External: last.ExternalMessageID})
		if err != nil {
			return Page{}, err
		}
		page.Items = items[:limit]
		page.NextCursor = &value
	}
	return page, nil
}

func encodeCursor(value cursor) (string, error) {
	encoded, err := json.Marshal(value)
	if err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(encoded), nil
}

func decodeCursor(value string) (cursor, error) {
	decoded, err := base64.RawURLEncoding.DecodeString(value)
	if err != nil {
		return cursor{}, err
	}
	var result cursor
	if err := json.Unmarshal(decoded, &result); err != nil {
		return cursor{}, err
	}
	if result.External == "" {
		return cursor{}, errors.New("invalid cursor")
	}
	return result, nil
}
