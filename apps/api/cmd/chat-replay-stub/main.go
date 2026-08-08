package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"strings"
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
	mux.HandleFunc("GET /v1/chat-replay/pages", replay)
	log.Printf("Chat replay stub listening on %s", addr)
	log.Fatal(http.ListenAndServe(addr, mux))
}

func replay(w http.ResponseWriter, r *http.Request) {
	if !authorized(r) {
		writeProblem(w, http.StatusUnauthorized, "GATEWAY_UNAUTHORIZED", false, "invalid token")
		return
	}
	videoID := r.URL.Query().Get("videoId")
	continuation := r.URL.Query().Get("continuation")
	if strings.HasPrefix(videoID, "failchat") {
		mu.Lock()
		failures[videoID]++
		attempt := failures[videoID]
		mu.Unlock()
		if attempt == 1 {
			writeProblem(
				w,
				http.StatusServiceUnavailable,
				"YOUTUBE_TEMPORARILY_UNAVAILABLE",
				true,
				"temporary fixture failure",
			)
			return
		}
	}

	start := time.Date(2026, 1, 1, 0, 1, 0, 0, time.UTC)
	messages := []map[string]any{}
	var next any
	if continuation == "" {
		messages = []map[string]any{
			message("message-2", "Second user", "second page boundary", start.Add(2*time.Second)),
			message("message-1", "First user", "first message", start.Add(time.Second)),
		}
		next = "page-2"
	} else {
		messages = []map[string]any{
			message("message-3", "Third user", "third message", start.Add(3*time.Second)),
		}
		next = nil
	}
	writeJSON(w, http.StatusOK, map[string]any{"messages": messages, "continuation": next})
}

func authorized(r *http.Request) bool {
	token := os.Getenv("YSA_GATEWAY_STUB_TOKEN")
	if token == "" {
		token = "e2e-gateway-token"
	}
	return r.Header.Get("Authorization") == "Bearer "+token
}

func message(id, author, text string, publishedAt time.Time) map[string]any {
	return map[string]any{
		"id":              id,
		"authorChannelId": "author-" + id,
		"authorName":      author,
		"text":            text,
		"publishedAt":     publishedAt.Format(time.RFC3339Nano),
	}
}

func writeProblem(w http.ResponseWriter, status int, code string, retryable bool, detail string) {
	writeJSON(w, status, map[string]any{
		"type":      "urn:youtube-stream-analyzer:gateway:" + strings.ToLower(code),
		"title":     code,
		"status":    status,
		"detail":    detail,
		"code":      code,
		"retryable": retryable,
		"requestId": "e2e-request",
	})
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}
