package reservation

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/tsumasaki-kurageya/youtube-stream-analyzer/apps/api/internal/youtube"
)

type Handler struct {
	youtube    *youtube.Client
	repository *Repository
	now        func() time.Time
}

func NewHandler(client *youtube.Client, repository *Repository) *Handler {
	return &Handler{youtube: client, repository: repository, now: time.Now}
}

type createRequest struct { URL string `json:"url"` }

func (h *Handler) Create(w http.ResponseWriter, r *http.Request) {
	var input createRequest
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 8<<10))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&input); err != nil || strings.TrimSpace(input.URL) == "" {
		writeProblem(w, http.StatusBadRequest, "INVALID_RESERVATION_URL", "YouTube URLを確認してください")
		return
	}
	videoID, err := youtube.VideoID(input.URL)
	if err != nil {
		writeProblem(w, http.StatusBadRequest, "INVALID_RESERVATION_URL", "対応するYouTube配信URLを入力してください")
		return
	}
	metadata, err := h.youtube.FetchReservation(r.Context(), videoID)
	if err != nil {
		writeYouTubeError(w, err)
		return
	}
	now := h.now().UTC()
	state := "monitoring"
	nextCheck := now
	switch {
	case metadata.ActualEndAt != nil:
		state = "waiting_for_archive"
		nextCheck = now.Add(time.Minute)
	case metadata.ActualStartAt != nil:
		state = "live"
		nextCheck = now.Add(30 * time.Second)
	case metadata.ScheduledStartAt != nil && metadata.ScheduledStartAt.After(now.Add(5*time.Minute)):
		state = "scheduled"
		nextCheck = metadata.ScheduledStartAt.Add(-5 * time.Minute)
	default:
		nextCheck = now.Add(time.Minute)
	}
	stored, err := h.repository.Create(r.Context(), CreateInput{
		YouTubeVideoID: videoID, SourceURL: input.URL, State: state,
		ScheduledStartAt: metadata.ScheduledStartAt, ActualStartAt: metadata.ActualStartAt,
		ActualEndAt: metadata.ActualEndAt, NextCheckAt: nextCheck,
	})
	if err != nil {
		if errors.Is(err, ErrAlreadyActive) {
			writeProblem(w, http.StatusConflict, "RESERVATION_ALREADY_ACTIVE", "この配信には有効な予約があります")
			return
		}
		writeProblem(w, http.StatusInternalServerError, "INTERNAL_ERROR", "予約を作成できませんでした")
		return
	}
	w.Header().Set("Location", "/api/reservations/"+stored.ID)
	writeJSON(w, http.StatusCreated, response(stored))
}

func (h *Handler) List(w http.ResponseWriter, r *http.Request) {
	state := r.URL.Query().Get("state")
	if state != "" && !validState(state) {
		writeProblem(w, http.StatusBadRequest, "INVALID_RESERVATION_STATE", "予約状態が不正です")
		return
	}
	limit, ok := queryInt(r, "limit", 50, 1, 100)
	if !ok { writeProblem(w, http.StatusBadRequest, "INVALID_PAGINATION", "limitを確認してください"); return }
	offset, ok := queryInt(r, "offset", 0, 0, 1_000_000)
	if !ok { writeProblem(w, http.StatusBadRequest, "INVALID_PAGINATION", "offsetを確認してください"); return }
	items, total, err := h.repository.List(r.Context(), state, limit, offset)
	if err != nil { writeProblem(w, http.StatusInternalServerError, "INTERNAL_ERROR", "予約一覧を取得できませんでした"); return }
	payload := make([]map[string]any, 0, len(items))
	for _, item := range items { payload = append(payload, response(item)) }
	writeJSON(w, http.StatusOK, map[string]any{"items":payload,"total":total,"limit":limit,"offset":offset})
}

func (h *Handler) Detail(w http.ResponseWriter, r *http.Request) {
	value, err := h.repository.Get(r.Context(), r.PathValue("reservationId"))
	if errors.Is(err, ErrNotFound) { writeProblem(w, http.StatusNotFound, "RESERVATION_NOT_FOUND", "予約が見つかりません"); return }
	if err != nil { writeProblem(w, http.StatusInternalServerError, "INTERNAL_ERROR", "予約を取得できませんでした"); return }
	writeJSON(w, http.StatusOK, response(value))
}

func (h *Handler) Cancel(w http.ResponseWriter, r *http.Request) {
	value, err := h.repository.Cancel(r.Context(), r.PathValue("reservationId"))
	switch {
	case errors.Is(err, ErrNotFound):
		writeProblem(w, http.StatusNotFound, "RESERVATION_NOT_FOUND", "予約が見つかりません")
	case errors.Is(err, ErrNotCancellable):
		writeProblem(w, http.StatusConflict, "RESERVATION_NOT_CANCELLABLE", "この状態の予約はキャンセルできません")
	case err != nil:
		writeProblem(w, http.StatusInternalServerError, "INTERNAL_ERROR", "予約をキャンセルできませんでした")
	default:
		writeJSON(w, http.StatusOK, response(value))
	}
}

func response(value Reservation) map[string]any {
	result := map[string]any{
		"id":value.ID,"youtubeVideoId":value.YouTubeVideoID,"sourceUrl":value.SourceURL,
		"state":value.State,"nextCheckAt":value.NextCheckAt,"monitorAttempt":value.MonitorAttempt,
		"canCancel":value.State=="scheduled"||value.State=="monitoring"||value.State=="live"||value.State=="waiting_for_archive",
		"createdAt":value.CreatedAt,"updatedAt":value.UpdatedAt,
		"scheduledStartAt":value.ScheduledStartAt,"actualStartAt":value.ActualStartAt,"actualEndAt":value.ActualEndAt,
		"lastCheckedAt":value.LastCheckedAt,"lastErrorCode":value.LastErrorCode,
		"lastErrorMessage":value.LastErrorMessage,"lastErrorRetryable":value.LastErrorRetryable,
		"streamId":value.StreamID,"collectionJobId":value.CollectionJobID,"collectionStatus":value.CollectionStatus,
		"collectionErrorCode":value.CollectionErrorCode,"collectionErrorMessage":value.CollectionErrorMessage,
		"cancelledAt":value.CancelledAt,"completedAt":value.CompletedAt,"failedAt":value.FailedAt,
	}
	return result
}

func queryInt(r *http.Request, name string, fallback, min, max int) (int, bool) {
	raw := r.URL.Query().Get(name); if raw == "" { return fallback, true }
	value, err := strconv.Atoi(raw); return value, err == nil && value >= min && value <= max
}
func validState(value string) bool { switch value { case "scheduled","monitoring","live","waiting_for_archive","collecting","completed","cancelled","failed": return true }; return false }
func writeJSON(w http.ResponseWriter, status int, value any) { w.Header().Set("Content-Type","application/json"); w.WriteHeader(status); _=json.NewEncoder(w).Encode(value) }
func writeProblem(w http.ResponseWriter, status int, code, title string) { w.Header().Set("Content-Type","application/problem+json"); w.WriteHeader(status); _=json.NewEncoder(w).Encode(map[string]any{"type":"about:blank","title":title,"status":status,"code":code}) }
func writeYouTubeError(w http.ResponseWriter, err error) {
	var gateway *youtube.GatewayError
	if !errors.As(err,&gateway) { writeProblem(w,http.StatusInternalServerError,"INTERNAL_ERROR","予約対象を確認できませんでした"); return }
	switch gateway.Code {
	case youtube.CodeVideoNotFound: writeProblem(w,http.StatusNotFound,"RESERVATION_VIDEO_NOT_FOUND","動画が見つかりません")
	case youtube.CodeAccessDenied: writeProblem(w,http.StatusForbidden,string(gateway.Code),"YouTubeへのアクセスが拒否されました")
	case youtube.CodeQuotaExceeded: writeProblem(w,http.StatusTooManyRequests,string(gateway.Code),"YouTube APIの利用上限に達しました")
	default: writeProblem(w,http.StatusServiceUnavailable,string(gateway.Code),"YouTubeの状態を確認できませんでした")
	}
}
