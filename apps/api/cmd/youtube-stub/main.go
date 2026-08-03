package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
)

var (
	requestMu     sync.Mutex
	requestCounts = map[string]int{}
)

func main() {
	addr := os.Getenv("YSA_YOUTUBE_STUB_ADDRESS")
	if addr == "" {
		addr = ":18080"
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /videos", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		videoID := r.URL.Query().Get("id")
		switch videoID {
		case "quotaerror1":
			w.WriteHeader(http.StatusForbidden)
			_, _ = fmt.Fprint(w, `{"error":{"errors":[{"reason":"quotaExceeded"}]}}`)
		case "accesserr01":
			w.WriteHeader(http.StatusForbidden)
			_, _ = fmt.Fprint(w, `{"error":{"errors":[{"reason":"forbidden"}]}}`)
		case "notended01x":
			_, _ = fmt.Fprint(w, `{"items":[{"id":"notended01x","snippet":{"title":"Live"},"contentDetails":{"duration":"PT1M"},"liveStreamingDetails":{"actualStartTime":"2026-01-01T00:00:00Z"}}]}`)
		default:
			if strings.HasPrefix(videoID, "m4") {
				writeM4Fixture(w, videoID)
				return
			}
			_, _ = fmt.Fprintf(w, `{"items":[{"id":%q,"snippet":{"title":"Stub stream","channelId":"stub-channel","channelTitle":"Stub creator","publishedAt":"2026-01-01T00:00:00Z","thumbnails":{"high":{"url":"https://example.test/thumb.jpg"}}},"contentDetails":{"duration":"PT1H2M3S"},"liveStreamingDetails":{"scheduledStartTime":"2026-01-01T00:00:00Z","actualStartTime":"2026-01-01T00:01:00Z","actualEndTime":"2026-01-01T01:03:03Z"}}]}`, videoID)
		}
	})
	log.Printf("YouTube API stub listening on %s", addr)
	log.Fatal(http.ListenAndServe(addr, mux))
}

func writeM4Fixture(w http.ResponseWriter, videoID string) {
	attempt := incrementRequestCount(videoID)
	if strings.HasPrefix(videoID, "m4monfail") && attempt > 1 {
		http.Error(w, "temporary archive fixture failure", http.StatusServiceUnavailable)
		return
	}

	now := time.Now().UTC().Truncate(time.Second)
	details := map[string]any{}
	status := map[string]any{"uploadStatus": "uploaded", "privacyStatus": "public"}
	contentDetails := map[string]any{"duration": ""}

	switch {
	case strings.HasPrefix(videoID, "m4sched"):
		details["scheduledStartTime"] = now.Add(time.Hour).Format(time.RFC3339)
	case strings.HasPrefix(videoID, "m4live"):
		details["scheduledStartTime"] = now.Add(-10 * time.Minute).Format(time.RFC3339)
		details["actualStartTime"] = now.Add(-5 * time.Minute).Format(time.RFC3339)
	default:
		details["scheduledStartTime"] = now.Add(-70 * time.Minute).Format(time.RFC3339)
		details["actualStartTime"] = now.Add(-60 * time.Minute).Format(time.RFC3339)
		details["actualEndTime"] = now.Add(-10 * time.Second).Format(time.RFC3339)
		status["uploadStatus"] = "processed"
		contentDetails["duration"] = "PT59M50S"
	}

	payload := map[string]any{
		"items": []any{map[string]any{
			"id": videoID,
			"snippet": map[string]any{
				"title":        "M4 deterministic fixture",
				"channelId":    "m4-fixture-channel",
				"channelTitle": "M4 fixture creator",
				"publishedAt":  now.Add(-2 * time.Hour).Format(time.RFC3339),
				"thumbnails": map[string]any{
					"high": map[string]any{"url": "https://example.test/m4-thumb.jpg"},
				},
			},
			"status":               status,
			"contentDetails":       contentDetails,
			"liveStreamingDetails": details,
		}},
	}
	_ = json.NewEncoder(w).Encode(payload)
}

func incrementRequestCount(videoID string) int {
	requestMu.Lock()
	defer requestMu.Unlock()
	requestCounts[videoID]++
	return requestCounts[videoID]
}
