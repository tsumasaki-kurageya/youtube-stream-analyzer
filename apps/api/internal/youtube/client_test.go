package youtube

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestFetchEndedLiveStream(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Get("key") != "test-key" { t.Fatal("missing API key") }
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"items":[{"id":"abcdefghijk","snippet":{"title":"stream","channelId":"channel","channelTitle":"creator","publishedAt":"2026-01-01T00:00:00Z","thumbnails":{"high":{"url":"https://example.test/thumb.jpg"}}},"contentDetails":{"duration":"PT2H3M4S"},"liveStreamingDetails":{"scheduledStartTime":"2026-01-01T00:00:00Z","actualStartTime":"2026-01-01T00:01:00Z","actualEndTime":"2026-01-01T02:04:04Z"}}]}`))
	}))
	defer server.Close()

	client, err := NewClient("test-key", server.URL, time.Second)
	if err != nil { t.Fatal(err) }
	metadata, err := client.Fetch(context.Background(), "abcdefghijk")
	if err != nil { t.Fatal(err) }
	if metadata.DurationSeconds != 7384 || metadata.Title != "stream" || metadata.ThumbnailURL == "" {
		t.Fatalf("unexpected metadata: %+v", metadata)
	}
}

func TestFetchErrorClassification(t *testing.T) {
	tests := []struct { status int; body string; code ErrorCode }{
		{http.StatusForbidden, `{"error":{"errors":[{"reason":"quotaExceeded"}]}}`, CodeQuotaExceeded},
		{http.StatusForbidden, `{"error":{"errors":[{"reason":"forbidden"}]}}`, CodeAccessDenied},
		{http.StatusNotFound, `{}`, CodeVideoNotFound},
		{http.StatusServiceUnavailable, `{}`, CodeTemporarilyUnavailable},
	}
	for _, test := range tests {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(test.status); _, _ = w.Write([]byte(test.body)) }))
		client, _ := NewClient("secret-key", server.URL, time.Second)
		_, err := client.Fetch(context.Background(), "abcdefghijk")
		server.Close()
		var gatewayErr *GatewayError
		if !errors.As(err, &gatewayErr) || gatewayErr.Code != test.code { t.Fatalf("error = %v; want %s", err, test.code) }
		if err.Error() == "secret-key" { t.Fatal("API key leaked") }
	}
}

func TestParseDuration(t *testing.T) {
	for input, want := range map[string]int64{"PT0S": 0, "PT1H2M3S": 3723, "P1DT2H": 93600} {
		got, err := ParseDuration(input)
		if err != nil || got != want { t.Fatalf("ParseDuration(%q) = %d, %v; want %d", input, got, err, want) }
	}
	if _, err := ParseDuration("not-a-duration"); err == nil { t.Fatal("expected error") }
}

func TestFetchRejectsNonEndedVideo(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { _, _ = w.Write([]byte(`{"items":[{"id":"abcdefghijk","snippet":{},"contentDetails":{"duration":"PT1S"}}]}`)) }))
	defer server.Close()
	client, _ := NewClient("key", server.URL, time.Second)
	_, err := client.Fetch(context.Background(), "abcdefghijk")
	var gatewayErr *GatewayError
	if !errors.As(err, &gatewayErr) || gatewayErr.Code != CodeNotEndedLiveStream { t.Fatalf("error = %v", err) }
}
