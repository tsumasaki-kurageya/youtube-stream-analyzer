package stream

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/tsumasaki-kurageya/youtube-stream-analyzer/apps/api/internal/platform"
	"github.com/tsumasaki-kurageya/youtube-stream-analyzer/apps/api/internal/youtube"
)

func TestRegisterHandlerIsIdempotentAndConcurrent(t *testing.T) {
	databaseURL := os.Getenv("YSA_TEST_DATABASE_URL")
	if databaseURL == "" {
		t.Skip("YSA_TEST_DATABASE_URL is not set")
	}

	db, err := platform.OpenDatabase(context.Background(), databaseURL)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	if _, err := db.Exec(context.Background(), "TRUNCATE stream.streams CASCADE"); err != nil {
		t.Fatal(err)
	}

	stub := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"items":[{"id":"abcdefghijk","snippet":{"title":"Test stream","channelId":"channel","channelTitle":"Channel","publishedAt":"2026-01-01T09:00:00Z","thumbnails":{"high":{"url":"https://example.com/thumb.jpg"}}},"contentDetails":{"duration":"PT2H"},"liveStreamingDetails":{"actualStartTime":"2026-01-01T10:00:00Z","actualEndTime":"2026-01-01T12:00:00Z"}}]}`))
	}))
	defer stub.Close()

	client, err := youtube.NewClient("test-key", stub.URL, 2*time.Second)
	if err != nil {
		t.Fatal(err)
	}
	handler := NewRegisterHandler(client, NewRepository(db))

	const workers = 6
	statuses := make(chan int, workers)
	ids := make(chan string, workers)
	var wg sync.WaitGroup
	for range workers {
		wg.Add(1)
		go func() {
			defer wg.Done()
			req := httptest.NewRequest(http.MethodPost, "/api/streams", strings.NewReader(`{"url":"https://youtu.be/abcdefghijk"}`))
			res := httptest.NewRecorder()
			handler.ServeHTTP(res, req)
			statuses <- res.Code
			ids <- res.Header().Get("Location")
		}()
	}
	wg.Wait()
	close(statuses)
	close(ids)

	createdCount := 0
	var location string
	for status := range statuses {
		if status == http.StatusCreated {
			createdCount++
		} else if status != http.StatusOK {
			t.Fatalf("unexpected status: %d", status)
		}
	}
	if createdCount != 1 {
		t.Fatalf("created responses = %d, want 1", createdCount)
	}
	for current := range ids {
		if current == "" {
			t.Fatal("Location header is empty")
		}
		if location == "" {
			location = current
		} else if current != location {
			t.Fatalf("different canonical locations: %s and %s", location, current)
		}
	}

	var count int
	if err := db.QueryRow(context.Background(), "SELECT count(*) FROM stream.streams WHERE youtube_video_id = $1", "abcdefghijk").Scan(&count); err != nil {
		t.Fatal(err)
	}
	if count != 1 {
		t.Fatalf("stored rows = %d, want 1", count)
	}
}
