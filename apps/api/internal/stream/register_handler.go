package stream

import (
	"encoding/json"
	"net/http"

	"github.com/tsumasaki-kurageya/youtube-stream-analyzer/apps/api/internal/youtube"
)

type RegisterHandler struct {
	youtube    *youtube.Client
	repository *Repository
}

func NewRegisterHandler(client *youtube.Client, repository *Repository) *RegisterHandler {
	return &RegisterHandler{youtube: client, repository: repository}
}

func (h *RegisterHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
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

	metadata, err := h.youtube.Fetch(r.Context(), videoID)
	if err != nil {
		status, code, title := mapGatewayError(err)
		writeProblem(w, status, code, title)
		return
	}

	stored, created, err := h.repository.Register(r.Context(), Stream{
		YouTubeVideoID:   metadata.YouTubeVideoID,
		SourceURL:        input.URL,
		Title:            metadata.Title,
		ChannelID:        metadata.ChannelID,
		ChannelTitle:     metadata.ChannelTitle,
		ThumbnailURL:     metadata.ThumbnailURL,
		ScheduledStartAt: metadata.ScheduledStartAt,
		ActualStartAt:    metadata.ActualStartAt,
		ActualEndAt:      metadata.ActualEndAt,
		DurationSeconds:  metadata.DurationSeconds,
		PublishedAt:      metadata.PublishedAt,
	})
	if err != nil {
		writeProblem(w, http.StatusInternalServerError, "INTERNAL_ERROR", "配信を登録できませんでした")
		return
	}

	location := "/api/streams/" + stored.ID
	w.Header().Set("Location", location)
	w.Header().Set("Content-Type", "application/json")
	if created {
		w.WriteHeader(http.StatusCreated)
	} else {
		w.WriteHeader(http.StatusOK)
	}
	_ = json.NewEncoder(w).Encode(streamResponse(stored))
}

func streamResponse(value Stream) map[string]any {
	result := map[string]any{
		"id":              value.ID,
		"youtubeVideoId":  value.YouTubeVideoID,
		"sourceUrl":       value.SourceURL,
		"title":           value.Title,
		"channelId":       value.ChannelID,
		"channelTitle":    value.ChannelTitle,
		"thumbnailUrl":    value.ThumbnailURL,
		"actualStartAt":   value.ActualStartAt,
		"actualEndAt":     value.ActualEndAt,
		"durationSeconds": value.DurationSeconds,
		"createdAt":       value.CreatedAt,
		"updatedAt":       value.UpdatedAt,
	}
	if value.ScheduledStartAt != nil {
		result["scheduledStartAt"] = value.ScheduledStartAt
	}
	if value.PublishedAt != nil {
		result["publishedAt"] = value.PublishedAt
	}
	return result
}
