package transcript

import (
	"context"
	"fmt"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

func TestListUsesStableCursorPagingAndRangeFilters(t *testing.T) {
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

	videoID := fmt.Sprintf("tx%09d", time.Now().UnixNano()%1000000000)
	var streamID string
	if err := db.QueryRow(ctx, `INSERT INTO stream.streams(youtube_video_id,source_url,title,channel_id,channel_title,thumbnail_url,actual_start_at,actual_end_at,duration_seconds) VALUES($1,$2,'transcript test','channel','creator','https://example.test/t.jpg',now()-interval '1 hour',now(),3600) RETURNING id`, videoID, "https://youtu.be/"+videoID).Scan(&streamID); err != nil {
		t.Fatal(err)
	}
	defer db.Exec(ctx, `DELETE FROM stream.streams WHERE id=$1`, streamID)

	var jobID, stepID, trackID string
	if err := db.QueryRow(ctx, `INSERT INTO collection.collection_jobs(stream_id,status) VALUES($1,'succeeded') RETURNING id`, streamID).Scan(&jobID); err != nil {
		t.Fatal(err)
	}
	if err := db.QueryRow(ctx, `INSERT INTO collection.collection_steps(job_id,name,status) VALUES($1,'transcript','succeeded') RETURNING id`, jobID).Scan(&stepID); err != nil {
		t.Fatal(err)
	}
	if err := db.QueryRow(ctx, `INSERT INTO transcript.transcript_tracks(stream_id,external_track_id,language_code,display_name,is_auto_generated,is_selected,collected_by_step_id) VALUES($1,'ja','ja','日本語',false,true,$2) RETURNING id`, streamID, stepID).Scan(&trackID); err != nil {
		t.Fatal(err)
	}
	for _, item := range []struct {
		id         string
		start, end int64
	}{
		{"b", 1000, 1700}, {"a", 1000, 1600}, {"c", 2000, 2800},
	} {
		if _, err := db.Exec(ctx, `INSERT INTO transcript.transcript_segments(stream_id,track_id,source_segment_id,start_offset_milliseconds,end_offset_milliseconds,text,normalized_text,collected_by_step_id) VALUES($1,$2,$3,$4,$5,$3,$3,$6)`, streamID, trackID, item.id, item.start, item.end, stepID); err != nil {
			t.Fatal(err)
		}
	}

	repository := NewRepository(db)
	first, err := repository.List(ctx, streamID, 2, "", nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(first.Items) != 2 || first.NextCursor == nil {
		t.Fatalf("unexpected first page: %#v", first)
	}
	second, err := repository.List(ctx, streamID, 2, *first.NextCursor, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(second.Items) != 1 || second.Items[0].SourceSegmentID != "c" {
		t.Fatalf("unexpected second page: %#v", second)
	}

	fromMS, toMS := int64(1500), int64(2100)
	overlap, err := repository.List(ctx, streamID, 10, "", &fromMS, &toMS)
	if err != nil {
		t.Fatal(err)
	}
	if len(overlap.Items) != 3 {
		t.Fatalf("expected three overlapping segments, got %#v", overlap)
	}
}
