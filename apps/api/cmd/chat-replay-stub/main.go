package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"strconv"
	"sync"
	"time"
)

var (
	mu       sync.Mutex
	failures = map[string]int{}
)

func main() {
	addr := os.Getenv("YSA_CHAT_REPLAY_STUB_ADDRESS")
	if addr == "" {
		addr = ":18081"
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /replay", replay)
	log.Printf("Chat replay stub listening on %s", addr)
	log.Fatal(http.ListenAndServe(addr, mux))
}

func replay(w http.ResponseWriter, r *http.Request) {
	videoID := r.URL.Query().Get("videoId")
	continuation := r.URL.Query().Get("continuation")
	if videoID == "failchat001" {
		mu.Lock()
		failures[videoID]++
		attempt := failures[videoID]
		mu.Unlock()
		if attempt == 1 {
			http.Error(w, "temporary fixture failure", http.StatusServiceUnavailable)
			return
		}
	}

	start := time.Date(2026, 1, 1, 0, 1, 0, 0, time.UTC)
	payload := map[string]any{"actions": []any{}}
	if continuation == "" {
		payload["actions"] = []any{
			message("message-2", "Second user", "second page boundary", start.Add(2*time.Second)),
			message("message-1", "First user", "first message", start.Add(time.Second)),
		}
		payload["continuation"] = "page-2"
	} else {
		payload["actions"] = []any{
			message("message-3", "Third user", "third message", start.Add(3*time.Second)),
		}
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(payload)
}

func message(id, author, text string, publishedAt time.Time) map[string]any {
	return map[string]any{
		"addChatItemAction": map[string]any{
			"item": map[string]any{
				"liveChatTextMessageRenderer": map[string]any{
					"id": id,
					"authorExternalChannelId": "author-" + id,
					"authorName": map[string]any{"simpleText": author},
					"message": map[string]any{"runs": []any{map[string]any{"text": text}}},
					"timestampUsec": strconv.FormatInt(publishedAt.UnixMicro(), 10),
				},
			},
		},
	}
}
