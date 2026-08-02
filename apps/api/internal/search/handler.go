package search

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"
)

type Handler struct{ repository *Repository }

func NewHandler(repository *Repository) *Handler { return &Handler{repository: repository} }

func (h *Handler) Search(w http.ResponseWriter, r *http.Request) {
	query := strings.TrimSpace(r.URL.Query().Get("q"))
	if len([]rune(query)) < 1 || len([]rune(query)) > 200 {
		writeProblem(
			w,
			http.StatusUnprocessableEntity,
			"INVALID_SEARCH_QUERY",
			"検索語は1〜200文字で指定してください",
		)
		return
	}
	limit := 50
	if raw := r.URL.Query().Get("limit"); raw != "" {
		value, err := strconv.Atoi(raw)
		if err != nil || value < 1 || value > 100 {
			writeProblem(
				w,
				http.StatusUnprocessableEntity,
				"INVALID_SEARCH_QUERY",
				"ページ件数は1〜100で指定してください",
			)
			return
		}
		limit = value
	}
	page, err := h.repository.Search(
		r.Context(),
		r.PathValue("streamId"),
		query,
		limit,
		r.URL.Query().Get("cursor"),
	)
	if err != nil {
		switch {
		case errors.Is(err, ErrStreamNotFound):
			writeProblem(w, http.StatusNotFound, "STREAM_NOT_FOUND", "配信が見つかりません")
		case errors.Is(err, ErrInvalidCursor):
			writeProblem(
				w,
				http.StatusUnprocessableEntity,
				"INVALID_CURSOR",
				"検索結果のページ位置が不正です",
			)
		default:
			writeProblem(
				w,
				http.StatusInternalServerError,
				"INTERNAL_ERROR",
				"検索を完了できませんでした",
			)
		}
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(page)
}

func writeProblem(w http.ResponseWriter, status int, code, title string) {
	w.Header().Set("Content-Type", "application/problem+json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"type": "about:blank", "title": title, "status": status, "code": code,
	})
}
