package stream

import (
	"encoding/json"
	"errors"
	"net/http"

	"github.com/tsumasaki-kurageya/youtube-stream-analyzer/apps/api/internal/youtube"
)

type PreviewService interface {
	Fetch(rctx interface{ Done() <-chan struct{} }, videoID string) (youtube.Metadata, error)
}

type youtubeFetcher interface {
	Fetch(ctx interface{ Done() <-chan struct{} }, videoID string) (youtube.Metadata, error)
}

type PreviewHandler struct {
	fetch func(*http.Request, string) (youtube.Metadata, error)
}

func NewPreviewHandler(client *youtube.Client) *PreviewHandler {
	return &PreviewHandler{fetch: func(r *http.Request, id string) (youtube.Metadata, error) {
		return client.Fetch(r.Context(), id)
	}}
}

type previewRequest struct {
	URL string `json:"url"`
}

type problemDetails struct {
	Type   string `json:"type"`
	Title  string `json:"title"`
	Status int    `json:"status"`
	Detail string `json:"detail,omitempty"`
	Code   string `json:"code"`
}

func (h *PreviewHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.WriteHeader(http.StatusMethodNotAllowed)
		return
	}
	var input previewRequest
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 8<<10))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&input); err != nil {
		writeProblem(w, http.StatusBadRequest, "INVALID_YOUTUBE_URL", "YouTube URLを確認してください")
		return
	}
	videoID, err := youtube.VideoID(input.URL)
	if err != nil {
		writeProblem(w, http.StatusBadRequest, "INVALID_YOUTUBE_URL", "対応するYouTube配信URLを入力してください")
		return
	}
	metadata, err := h.fetch(r, videoID)
	if err != nil {
		status, code, title := mapGatewayError(err)
		writeProblem(w, status, code, title)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(metadataResponse(metadata))
}

func metadataResponse(value youtube.Metadata) map[string]any {
	result := map[string]any{
		"youtubeVideoId": value.YouTubeVideoID,
		"title": value.Title,
		"channelId": value.ChannelID,
		"channelTitle": value.ChannelTitle,
		"thumbnailUrl": value.ThumbnailURL,
		"actualStartAt": value.ActualStartAt,
		"actualEndAt": value.ActualEndAt,
		"durationSeconds": value.DurationSeconds,
	}
	if value.ScheduledStartAt != nil { result["scheduledStartAt"] = value.ScheduledStartAt }
	if value.PublishedAt != nil { result["publishedAt"] = value.PublishedAt }
	return result
}

func mapGatewayError(err error) (int, string, string) {
	var gateway *youtube.GatewayError
	if !errors.As(err, &gateway) {
		return http.StatusInternalServerError, "INTERNAL_ERROR", "配信情報を取得できませんでした"
	}
	switch gateway.Code {
	case youtube.CodeVideoNotFound:
		return http.StatusNotFound, string(gateway.Code), "動画が見つかりません"
	case youtube.CodeNotEndedLiveStream:
		return http.StatusUnprocessableEntity, string(gateway.Code), "終了済みライブ配信ではありません"
	case youtube.CodeAccessDenied:
		return http.StatusForbidden, string(gateway.Code), "YouTubeへのアクセスが拒否されました"
	case youtube.CodeQuotaExceeded:
		return http.StatusTooManyRequests, string(gateway.Code), "YouTube APIの利用上限に達しました"
	default:
		return http.StatusServiceUnavailable, string(youtube.CodeTemporarilyUnavailable), "YouTubeから一時的に情報を取得できません"
	}
}

func writeProblem(w http.ResponseWriter, status int, code, title string) {
	w.Header().Set("Content-Type", "application/problem+json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(problemDetails{Type: "about:blank", Title: title, Status: status, Code: code})
}
