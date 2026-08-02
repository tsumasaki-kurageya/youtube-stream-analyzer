package transcript

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
)

type Handler struct{ repository *Repository }

func NewHandler(repository *Repository) *Handler { return &Handler{repository: repository} }

func (h *Handler) List(w http.ResponseWriter, r *http.Request) {
	limit := 100
	if raw := r.URL.Query().Get("limit"); raw != "" {
		value, err := strconv.Atoi(raw)
		if err != nil || value < 1 || value > 200 {
			writeProblem(w, http.StatusBadRequest, "INVALID_PAGINATION", "limitは1から200の範囲で指定してください")
			return
		}
		limit = value
	}
	page, err := h.repository.List(r.Context(), r.PathValue("streamId"), limit, r.URL.Query().Get("cursor"))
	if err != nil {
		handleError(w, err, r.URL.Query().Get("cursor") != "")
		return
	}
	writeJSON(w, page)
}

func (h *Handler) Range(w http.ResponseWriter, r *http.Request) {
	fromMS, err := strconv.ParseInt(r.URL.Query().Get("fromMs"), 10, 64)
	if err != nil || fromMS < 0 {
		writeProblem(w, http.StatusBadRequest, "INVALID_TIME_RANGE", "fromMsは0以上で指定してください")
		return
	}
	toMS, err := strconv.ParseInt(r.URL.Query().Get("toMs"), 10, 64)
	if err != nil || toMS <= fromMS || toMS-fromMS > 300000 {
		writeProblem(w, http.StatusBadRequest, "INVALID_TIME_RANGE", "toMsはfromMsより大きく、範囲は5分以内で指定してください")
		return
	}
	items, err := h.repository.Range(r.Context(), r.PathValue("streamId"), fromMS, toMS)
	if err != nil {
		handleError(w, err, false)
		return
	}
	writeJSON(w, map[string]any{"items": items, "fromMs": fromMS, "toMs": toMS})
}

func handleError(w http.ResponseWriter, err error, invalidCursor bool) {
	switch {
	case errors.Is(err, ErrStreamNotFound):
		writeProblem(w, http.StatusNotFound, "STREAM_NOT_FOUND", "配信が見つかりません")
	case invalidCursor:
		writeProblem(w, http.StatusBadRequest, "INVALID_CURSOR", "ページ位置が不正です")
	default:
		writeProblem(w, http.StatusInternalServerError, "INTERNAL_ERROR", "字幕を取得できませんでした")
	}
}

func writeJSON(w http.ResponseWriter, value any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(value)
}

func writeProblem(w http.ResponseWriter, status int, code, title string) {
	w.Header().Set("Content-Type", "application/problem+json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]any{"type": "about:blank", "title": title, "status": status, "code": code})
}
