package collection

import (
	"context"
	"errors"
	"fmt"
	"os"
	"sync"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

func testRepository(t *testing.T) (*Repository, *pgxpool.Pool, string) {
	t.Helper()
	url := os.Getenv("YSA_TEST_DATABASE_URL")
	if url == "" { t.Skip("YSA_TEST_DATABASE_URL is not set") }
	ctx := context.Background()
	db, err := pgxpool.New(ctx, url)
	if err != nil { t.Fatal(err) }
	t.Cleanup(db.Close)
	var streamID string
	videoID := fmt.Sprintf("job%08d", time.Now().UnixNano()%100000000)
	err = db.QueryRow(ctx, `INSERT INTO stream.streams(youtube_video_id,source_url,title,channel_id,channel_title,thumbnail_url,actual_start_at,actual_end_at,duration_seconds) VALUES($1,$2,'test','channel','creator','https://example.test/t.jpg',now()-interval '1 hour',now(),3600) RETURNING id`, videoID, "https://www.youtube.com/watch?v="+videoID).Scan(&streamID)
	if err != nil { t.Fatal(err) }
	t.Cleanup(func(){ _, _ = db.Exec(ctx, `DELETE FROM stream.streams WHERE id=$1`, streamID) })
	return NewRepository(db), db, streamID
}

func TestCreateAndLatest(t *testing.T) {
	repository, _, streamID := testRepository(t)
	ctx := context.Background()
	created, err := repository.Create(ctx, streamID)
	if err != nil { t.Fatal(err) }
	if created.Status != "queued" || created.Attempt != 1 || len(created.Steps) != 1 { t.Fatalf("unexpected job: %#v", created) }
	latest, err := repository.Latest(ctx, streamID)
	if err != nil { t.Fatal(err) }
	if latest.ID != created.ID { t.Fatalf("latest ID = %s, want %s", latest.ID, created.ID) }
}

func TestConcurrentCreateAllowsOnlyOneActiveJob(t *testing.T) {
	repository, _, streamID := testRepository(t)
	ctx := context.Background()
	var wg sync.WaitGroup
	results := make(chan error, 2)
	for range 2 { wg.Add(1); go func(){ defer wg.Done(); _, err := repository.Create(ctx, streamID); results <- err }() }
	wg.Wait(); close(results)
	success, conflict := 0, 0
	for err := range results { if err == nil { success++ } else if errors.Is(err, ErrConflict) { conflict++ } else { t.Fatal(err) } }
	if success != 1 || conflict != 1 { t.Fatalf("success=%d conflict=%d", success, conflict) }
}

func TestRetryFailedJobCreatesNewAttempt(t *testing.T) {
	repository, db, streamID := testRepository(t)
	ctx := context.Background()
	original, err := repository.Create(ctx, streamID)
	if err != nil { t.Fatal(err) }
	_, err = db.Exec(ctx, `UPDATE collection.collection_jobs SET status='failed', error_code='TEST' WHERE id=$1`, original.ID)
	if err != nil { t.Fatal(err) }
	retried, err := repository.Retry(ctx, original.ID)
	if err != nil { t.Fatal(err) }
	if retried.Attempt != 2 || retried.RetryOfJobID == nil || *retried.RetryOfJobID != original.ID { t.Fatalf("unexpected retry: %#v", retried) }
}
