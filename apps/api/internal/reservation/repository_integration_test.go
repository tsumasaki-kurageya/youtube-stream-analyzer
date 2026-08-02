package reservation

import (
	"context"
	"errors"
	"fmt"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

func TestReservationPersistenceDuplicateAndCancellation(t *testing.T) {
	url := os.Getenv("YSA_TEST_DATABASE_URL")
	if url == "" {
		t.Skip("YSA_TEST_DATABASE_URL is not set")
	}
	ctx := context.Background()
	db, err := pgxpool.New(ctx, url)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	repository := NewRepository(db)
	videoID := fmt.Sprintf("r%010d", time.Now().UnixNano()%10_000_000_000)
	nextCheck := time.Now().UTC().Add(time.Minute)
	created, err := repository.Create(ctx, CreateInput{
		YouTubeVideoID: videoID,
		SourceURL:      "https://www.youtube.com/watch?v=" + videoID,
		State:          "monitoring",
		NextCheckAt:    nextCheck,
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		_, _ = db.Exec(ctx, `DELETE FROM reservation.reservations WHERE id=$1`, created.ID)
	})

	loaded, err := repository.Get(ctx, created.ID)
	if err != nil {
		t.Fatal(err)
	}
	if loaded.YouTubeVideoID != videoID || loaded.State != "monitoring" || loaded.MonitorAttempt != 0 {
		t.Fatalf("unexpected reservation: %#v", loaded)
	}

	if _, err := repository.Create(ctx, CreateInput{
		YouTubeVideoID: videoID,
		SourceURL:      "https://youtu.be/" + videoID,
		State:          "scheduled",
		NextCheckAt:    nextCheck,
	}); !errors.Is(err, ErrAlreadyActive) {
		t.Fatalf("expected duplicate error, got %v", err)
	}

	items, total, err := repository.List(ctx, "monitoring", 10, 0)
	if err != nil {
		t.Fatal(err)
	}
	if total < 1 || len(items) < 1 || items[0].ID != created.ID {
		t.Fatalf("unexpected list result: total=%d items=%#v", total, items)
	}

	cancelled, err := repository.Cancel(ctx, created.ID)
	if err != nil {
		t.Fatal(err)
	}
	if cancelled.State != "cancelled" || cancelled.CancelledAt == nil {
		t.Fatalf("unexpected cancelled reservation: %#v", cancelled)
	}
	if _, err := repository.Cancel(ctx, created.ID); !errors.Is(err, ErrNotCancellable) {
		t.Fatalf("expected not cancellable, got %v", err)
	}

	var transitionCount int
	if err := db.QueryRow(ctx, `
		SELECT count(*) FROM reservation.reservation_transitions
		WHERE reservation_id=$1
	`, created.ID).Scan(&transitionCount); err != nil {
		t.Fatal(err)
	}
	if transitionCount != 2 {
		t.Fatalf("expected two transitions, got %d", transitionCount)
	}
}
