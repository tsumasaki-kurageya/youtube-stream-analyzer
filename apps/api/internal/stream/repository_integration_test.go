package stream_test

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/tsumasaki-kurageya/youtube-stream-analyzer/apps/api/internal/platform"
	"github.com/tsumasaki-kurageya/youtube-stream-analyzer/apps/api/internal/stream"
)

func TestRepositoryInsertGetList(t *testing.T) {
	databaseURL := os.Getenv("YSA_TEST_DATABASE_URL")
	if databaseURL == "" {
		t.Skip("YSA_TEST_DATABASE_URL is not set")
	}

	ctx := context.Background()
	db, err := platform.OpenDatabase(ctx, databaseURL)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	if _, err := db.Exec(ctx, "TRUNCATE stream.streams CASCADE"); err != nil {
		t.Fatal(err)
	}

	repo := stream.NewRepository(db)
	start := time.Date(2026, 1, 1, 10, 0, 0, 0, time.UTC)
	created, err := repo.Insert(ctx, stream.Stream{
		YouTubeVideoID:  "abcdefghijk",
		SourceURL:       "https://www.youtube.com/watch?v=abcdefghijk",
		Title:           "Test stream",
		ChannelID:       "channel-1",
		ChannelTitle:    "Test channel",
		ThumbnailURL:    "https://example.test/thumb.jpg",
		ActualStartAt:   start,
		ActualEndAt:     start.Add(time.Hour),
		DurationSeconds: 3600,
	})
	if err != nil {
		t.Fatal(err)
	}
	if created.ID == "" {
		t.Fatal("expected database-generated ID")
	}

	loaded, err := repo.Get(ctx, created.ID)
	if err != nil {
		t.Fatal(err)
	}
	if loaded.YouTubeVideoID != created.YouTubeVideoID {
		t.Fatalf("unexpected video ID: %s", loaded.YouTubeVideoID)
	}

	items, err := repo.List(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 {
		t.Fatalf("expected 1 stream, got %d", len(items))
	}

	existing, wasCreated, err := repo.Register(ctx, created)
	if err != nil {
		t.Fatal(err)
	}
	if wasCreated {
		t.Fatal("duplicate registration must not create a new row")
	}
	if existing.ID != created.ID {
		t.Fatalf("duplicate registration returned %s, want %s", existing.ID, created.ID)
	}
}
