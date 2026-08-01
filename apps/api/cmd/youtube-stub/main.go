package main

import (
	"fmt"
	"log"
	"net/http"
	"os"
)

func main() {
	addr := os.Getenv("YSA_YOUTUBE_STUB_ADDRESS")
	if addr == "" { addr = ":18080" }
	mux := http.NewServeMux()
	mux.HandleFunc("GET /videos", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Query().Get("id") {
		case "quotaerror1":
			w.WriteHeader(http.StatusForbidden)
			_, _ = fmt.Fprint(w, `{"error":{"errors":[{"reason":"quotaExceeded"}]}}`)
		case "accesserr01":
			w.WriteHeader(http.StatusForbidden)
			_, _ = fmt.Fprint(w, `{"error":{"errors":[{"reason":"forbidden"}]}}`)
		case "notended01x":
			_, _ = fmt.Fprint(w, `{"items":[{"id":"notended01x","snippet":{"title":"Live"},"contentDetails":{"duration":"PT1M"},"liveStreamingDetails":{"actualStartTime":"2026-01-01T00:00:00Z"}}]}`)
		default:
			_, _ = fmt.Fprintf(w, `{"items":[{"id":%q,"snippet":{"title":"Stub stream","channelId":"stub-channel","channelTitle":"Stub creator","publishedAt":"2026-01-01T00:00:00Z","thumbnails":{"high":{"url":"https://example.test/thumb.jpg"}}},"contentDetails":{"duration":"PT1H2M3S"},"liveStreamingDetails":{"scheduledStartTime":"2026-01-01T00:00:00Z","actualStartTime":"2026-01-01T00:01:00Z","actualEndTime":"2026-01-01T01:03:03Z"}}]}`, r.URL.Query().Get("id"))
		}
	})
	log.Printf("YouTube API stub listening on %s", addr)
	log.Fatal(http.ListenAndServe(addr, mux))
}
