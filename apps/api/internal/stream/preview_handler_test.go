package stream

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/tsumasaki-kurageya/youtube-stream-analyzer/apps/api/internal/youtube"
)

func TestPreviewHandlerReturnsMetadata(t *testing.T) {
	handler := &PreviewHandler{fetch: func(_ *http.Request, videoID string) (youtube.Metadata, error) {
		if videoID != "abcdefghijk" { t.Fatalf("unexpected video id: %s", videoID) }
		return youtube.Metadata{
			YouTubeVideoID: videoID,
			Title: "Test stream",
			ChannelID: "channel",
			ChannelTitle: "Channel",
			ThumbnailURL: "https://example.com/thumb.jpg",
			ActualStartAt: time.Date(2026, 1, 1, 10, 0, 0, 0, time.UTC),
			ActualEndAt: time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC),
			DurationSeconds: 7200,
		}, nil
	}}

	request := httptest.NewRequest(http.MethodPost, "/api/streams/preview", strings.NewReader(`{"url":"https://youtu.be/abcdefghijk"}`))
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)

	if response.Code != http.StatusOK { t.Fatalf("status = %d, body = %s", response.Code, response.Body.String()) }
	if !strings.Contains(response.Body.String(), `"youtubeVideoId":"abcdefghijk"`) { t.Fatalf("unexpected body: %s", response.Body.String()) }
}

func TestPreviewHandlerRejectsInvalidURL(t *testing.T) {
	handler := &PreviewHandler{fetch: func(_ *http.Request, _ string) (youtube.Metadata, error) {
		t.Fatal("fetch must not be called")
		return youtube.Metadata{}, nil
	}}
	request := httptest.NewRequest(http.MethodPost, "/api/streams/preview", strings.NewReader(`{"url":"https://example.com/video"}`))
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusBadRequest { t.Fatalf("status = %d", response.Code) }
	if !strings.Contains(response.Body.String(), "INVALID_YOUTUBE_URL") { t.Fatalf("unexpected body: %s", response.Body.String()) }
}

func TestPreviewHandlerMapsGatewayError(t *testing.T) {
	handler := &PreviewHandler{fetch: func(_ *http.Request, _ string) (youtube.Metadata, error) {
		return youtube.Metadata{}, &youtube.GatewayError{Code: youtube.CodeNotEndedLiveStream}
	}}
	request := httptest.NewRequest(http.MethodPost, "/api/streams/preview", strings.NewReader(`{"url":"https://youtu.be/abcdefghijk"}`))
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code != http.StatusUnprocessableEntity { t.Fatalf("status = %d", response.Code) }
}

func TestMapGatewayErrorDoesNotExposeInternalError(t *testing.T) {
	status, code, _ := mapGatewayError(errors.New("secret api key"))
	if status != http.StatusInternalServerError || code != "INTERNAL_ERROR" { t.Fatalf("unexpected mapping: %d %s", status, code) }
}
