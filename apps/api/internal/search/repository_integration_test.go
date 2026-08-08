package search

import (
	"context"
	"fmt"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

func TestSearchReturnsChatAndTranscriptWithStableCursor(t *testing.T) {
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

	videoID := fmt.Sprintf("srch%07d", time.Now().UnixNano()%10000000)
	var streamID, jobID, stepID, trackID string
	if err := db.QueryRow(ctx, `
		INSERT INTO stream.streams(
			youtube_video_id,source_url,title,channel_id,channel_title,
			thumbnail_url,actual_start_at,actual_end_at,duration_seconds
		) VALUES($1,$2,'search test','channel','creator','https://example.test/t.jpg',
			now()-interval '1 hour',now(),3600)
		RETURNING id
	`, videoID, "https://youtu.be/"+videoID).Scan(&streamID); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _, _ = db.Exec(ctx, `DELETE FROM stream.streams WHERE id=$1`, streamID) })
	if err := db.QueryRow(ctx, `
		INSERT INTO collection.collection_jobs(stream_id,kind,status,requested_steps)
		VALUES($1,'full','succeeded',ARRAY['transcript']) RETURNING id
	`, streamID).Scan(&jobID); err != nil {
		t.Fatal(err)
	}
	if err := db.QueryRow(ctx, `
		INSERT INTO collection.collection_steps(job_id,name,status)
		VALUES($1,'transcript','succeeded') RETURNING id
	`, jobID).Scan(&stepID); err != nil {
		t.Fatal(err)
	}
	if err := db.QueryRow(ctx, `
		INSERT INTO transcript.transcript_tracks(
			stream_id,external_track_id,language_code,display_name,is_auto_generated,
			is_selected,collected_by_step_id
		) VALUES($1,'ja','ja','日本語',false,true,$2) RETURNING id
	`, streamID, stepID).Scan(&trackID); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(ctx, `
		INSERT INTO chat.chat_messages(
			stream_id,collection_job_id,external_message_id,author_name,message_text,
			published_at,elapsed_milliseconds
		) VALUES
			($1,$2,'m1','alice','検索対象のチャット',now(),1000),
			($1,$2,'m2','bob','検索対象の後続チャット',now(),3000)
	`, streamID, jobID); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(ctx, `
		INSERT INTO transcript.transcript_segments(
			stream_id,track_id,source_segment_id,start_offset_milliseconds,
			end_offset_milliseconds,text,normalized_text,collected_by_step_id
		) VALUES($1,$2,'s1',2000,2500,'検索対象の字幕','検索対象の字幕',$3)
	`, streamID, trackID, stepID); err != nil {
		t.Fatal(err)
	}

	repository := NewRepository(db)
	first, err := repository.Search(ctx, streamID, "検索対象", 2, "")
	if err != nil {
		t.Fatal(err)
	}
	if len(first.Items) != 2 || first.NextCursor == nil || !first.HasMore {
		t.Fatalf("unexpected first page: %#v", first)
	}
	if first.Items[0].Type != "chat" || first.Items[0].OffsetMilliseconds != 1000 ||
		first.Items[0].Speaker == nil || *first.Items[0].Speaker != "alice" {
		t.Fatalf("unexpected first item: %#v", first.Items[0])
	}
	if first.Items[1].Type != "transcript" || first.Items[1].OffsetMilliseconds != 2000 ||
		first.Items[1].EndOffsetMilliseconds == nil || *first.Items[1].EndOffsetMilliseconds != 2500 {
		t.Fatalf("unexpected second item: %#v", first.Items[1])
	}
	second, err := repository.Search(ctx, streamID, "検索対象", 2, *first.NextCursor)
	if err != nil {
		t.Fatal(err)
	}
	if len(second.Items) != 1 || second.Items[0].OffsetMilliseconds != 3000 || second.HasMore {
		t.Fatalf("unexpected second page: %#v", second)
	}
}
