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
	if url == "" {
		t.Skip("YSA_TEST_DATABASE_URL is not set")
	}
	ctx := context.Background()
	db, err := pgxpool.New(ctx, url)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(db.Close)
	var streamID string
	videoID := fmt.Sprintf("job%08d", time.Now().UnixNano()%100000000)
	err = db.QueryRow(ctx, `
		INSERT INTO stream.streams(
			youtube_video_id,source_url,title,channel_id,channel_title,
			thumbnail_url,actual_start_at,actual_end_at,duration_seconds
		) VALUES($1,$2,'test','channel','creator','https://example.test/t.jpg',
			now()-interval '1 hour',now(),3600)
		RETURNING id`, videoID, "https://www.youtube.com/watch?v="+videoID).Scan(&streamID)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		_, _ = db.Exec(ctx, `DELETE FROM stream.streams WHERE id=$1`, streamID)
	})
	return NewRepository(db), db, streamID
}

func TestCreateFullAndLatest(t *testing.T) {
	repository, _, streamID := testRepository(t)
	ctx := context.Background()
	created, err := repository.CreateFull(ctx, streamID)
	if err != nil {
		t.Fatal(err)
	}
	if created.Status != "queued" || created.Kind != "full" || len(created.Steps) != 3 {
		t.Fatalf("unexpected job: %#v", created)
	}
	if created.Steps[0].Name != "metadata" ||
		created.Steps[1].Name != "chat_replay" ||
		created.Steps[2].Name != "transcript" {
		t.Fatalf("unexpected step order: %#v", created.Steps)
	}
	latest, err := repository.Latest(ctx, streamID)
	if err != nil {
		t.Fatal(err)
	}
	if latest.ID != created.ID {
		t.Fatalf("latest ID = %s, want %s", latest.ID, created.ID)
	}
}

func TestConcurrentCreateAllowsOnlyOneActiveJob(t *testing.T) {
	repository, _, streamID := testRepository(t)
	ctx := context.Background()
	var wg sync.WaitGroup
	results := make(chan error, 2)
	for range 2 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, err := repository.CreateFull(ctx, streamID)
			results <- err
		}()
	}
	wg.Wait()
	close(results)
	success, conflict := 0, 0
	for err := range results {
		switch {
		case err == nil:
			success++
		case errors.Is(err, ErrConflict):
			conflict++
		default:
			t.Fatal(err)
		}
	}
	if success != 1 || conflict != 1 {
		t.Fatalf("success=%d conflict=%d", success, conflict)
	}
}

func TestRetryStepQueuesOnlyFailedRetryableStep(t *testing.T) {
	repository, db, streamID := testRepository(t)
	ctx := context.Background()
	job, err := repository.CreateFull(ctx, streamID)
	if err != nil {
		t.Fatal(err)
	}
	_, err = db.Exec(ctx, `
		UPDATE collection.collection_steps
		SET status=CASE WHEN name='transcript' THEN 'failed' ELSE 'succeeded' END,
		    retryable=CASE WHEN name='transcript' THEN true ELSE NULL END,
		    error_code=CASE WHEN name='transcript' THEN 'TEMPORARY' ELSE NULL END,
		    error_message=CASE WHEN name='transcript' THEN 'retry me' ELSE NULL END,
		    finished_at=now()
		WHERE job_id=$1`, job.ID)
	if err != nil {
		t.Fatal(err)
	}
	_, err = db.Exec(ctx, `
		UPDATE collection.collection_jobs SET status='partial',finished_at=now() WHERE id=$1`,
		job.ID,
	)
	if err != nil {
		t.Fatal(err)
	}

	retried, err := repository.RetryStep(ctx, job.ID, "transcript")
	if err != nil {
		t.Fatal(err)
	}
	if retried.Status != "queued" || retried.Attempt != 2 {
		t.Fatalf("unexpected retry: %#v", retried)
	}
	latest, err := repository.Latest(ctx, streamID)
	if err != nil {
		t.Fatal(err)
	}
	if latest.Status != "queued" {
		t.Fatalf("unexpected job status: %s", latest.Status)
	}
	for _, step := range latest.Steps {
		if step.Name != "transcript" && step.Status != "succeeded" {
			t.Fatalf("successful step was reset: %#v", step)
		}
	}
}
