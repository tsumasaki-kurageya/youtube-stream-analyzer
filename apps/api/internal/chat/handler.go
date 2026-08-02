package chat

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
		switch {
		case errors.Is(err, ErrStreamNotFound):
			writeProblem(w, http.StatusNotFound, "STREAM_NOT_FOUND", "配信が見つかりません")
		default:
			if r.URL.Query().Get("cursor") != "" {
				writeProblem(w, http.StatusBadRequest, "INVALID_CURSOR", "ページ位置が不正です")
				return
			}
			writeProblem(w, http.StatusInternalServerError, "INTERNAL_ERROR", "チャットを取得できませんでした")
		}
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(page)
}

func writeProblem(w http.ResponseWriter, status int, code, title string) {
	w.Header().Set("Content-Type", "application/problem+json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]any{"type": "about:blank", "title": title, "status": status, "code": code})
}
