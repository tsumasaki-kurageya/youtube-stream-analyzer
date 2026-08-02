package chat

import (
	"context"
	"fmt"
	"os"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

func TestListUsesStableCursorPagingAndTimeRange(t *testing.T) {
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

	videoID := fmt.Sprintf("chat%07d", time.Now().UnixNano()%10000000)
	var streamID string
	if err := db.QueryRow(ctx, `INSERT INTO stream.streams(youtube_video_id,source_url,title,channel_id,channel_title,thumbnail_url,actual_start_at,actual_end_at,duration_seconds) VALUES($1,$2,'chat test','channel','creator','https://example.test/t.jpg',now()-interval '1 hour',now(),3600) RETURNING id`, videoID, "https://youtu.be/"+videoID).Scan(&streamID); err != nil {
		t.Fatal(err)
	}
	defer db.Exec(ctx, `DELETE FROM stream.streams WHERE id=$1`, streamID)

	var jobID string
	if err := db.QueryRow(ctx, `INSERT INTO collection.collection_jobs(stream_id,status) VALUES($1,'succeeded') RETURNING id`, streamID).Scan(&jobID); err != nil {
		t.Fatal(err)
	}
	published := time.Now().UTC().Truncate(time.Millisecond)
	for _, item := range []struct {
		id      string
		elapsed int64
	}{
		{"b", 1000}, {"a", 1000}, {"c", 2000}, {"d", 5000},
	} {
		_, err := db.Exec(ctx, `INSERT INTO chat.chat_messages(stream_id,collection_job_id,external_message_id,author_name,message_text,published_at,elapsed_milliseconds) VALUES($1,$2,$3,'user',$3,$4,$5)`, streamID, jobID, item.id, published, item.elapsed)
		if err != nil {
			t.Fatal(err)
		}
	}

	repository := NewRepository(db)
	first, err := repository.List(ctx, streamID, 2, "", nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(first.Items) != 2 || first.Items[0].ExternalMessageID != "a" || first.Items[1].ExternalMessageID != "b" || first.NextCursor == nil {
		t.Fatalf("unexpected first page: %#v", first)
	}
	second, err := repository.List(ctx, streamID, 2, *first.NextCursor, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(second.Items) != 2 || second.Items[0].ExternalMessageID != "c" || second.Items[1].ExternalMessageID != "d" || second.NextCursor != nil {
		t.Fatalf("unexpected second page: %#v", second)
	}

	from, to := int64(1500), int64(3000)
	ranged, err := repository.List(ctx, streamID, 10, "", &from, &to)
	if err != nil {
		t.Fatal(err)
	}
	if len(ranged.Items) != 1 || ranged.Items[0].ExternalMessageID != "c" {
		t.Fatalf("unexpected ranged page: %#v", ranged)
	}
}
