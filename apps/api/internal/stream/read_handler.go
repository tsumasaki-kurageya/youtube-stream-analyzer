package stream

import (
	"encoding/json"
	"net/http"
	"strings"
)

type ReadHandler struct {
	repository *Repository
}

func NewReadHandler(repository *Repository) *ReadHandler {
	return &ReadHandler{repository: repository}
}

func (h *ReadHandler) List(w http.ResponseWriter, r *http.Request) {
	items, err := h.repository.List(r.Context())
	if err != nil {
		writeProblem(w, http.StatusInternalServerError, "INTERNAL_ERROR", "配信一覧を取得できませんでした")
		return
	}
	responses := make([]map[string]any, 0, len(items))
	for _, item := range items {
		responses = append(responses, streamResponse(item))
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"items": responses, "total": len(responses)})
}

func (h *ReadHandler) Detail(w http.ResponseWriter, r *http.Request) {
	id := strings.TrimSpace(r.PathValue("streamId"))
	if id == "" {
		writeProblem(w, http.StatusNotFound, "STREAM_NOT_FOUND", "配信が見つかりません")
		return
	}
	item, err := h.repository.Get(r.Context(), id)
	if err != nil {
		if IsNotFound(err) {
			writeProblem(w, http.StatusNotFound, "STREAM_NOT_FOUND", "配信が見つかりません")
			return
		}
		writeProblem(w, http.StatusInternalServerError, "INTERNAL_ERROR", "配信情報を取得できませんでした")
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(streamResponse(item))
}
