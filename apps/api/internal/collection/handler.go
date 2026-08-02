package collection

import (
	"encoding/json"
	"errors"
	"net/http"
)

type Handler struct{ repository *Repository }

func NewHandler(repository *Repository) *Handler { return &Handler{repository: repository} }

func (h *Handler) Start(w http.ResponseWriter, r *http.Request) {
	job, err := h.repository.Create(r.Context(), r.PathValue("streamId"))
	if err != nil { h.writeError(w, err); return }
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Location", "/api/collection-jobs/"+job.ID)
	w.WriteHeader(http.StatusAccepted)
	_ = json.NewEncoder(w).Encode(jobResponse(job))
}

func (h *Handler) Latest(w http.ResponseWriter, r *http.Request) {
	job, err := h.repository.Latest(r.Context(), r.PathValue("streamId"))
	if err != nil { h.writeError(w, err); return }
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(jobResponse(job))
}

func (h *Handler) Retry(w http.ResponseWriter, r *http.Request) {
	job, err := h.repository.Retry(r.Context(), r.PathValue("jobId"))
	if err != nil { h.writeError(w, err); return }
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Location", "/api/collection-jobs/"+job.ID)
	w.WriteHeader(http.StatusAccepted)
	_ = json.NewEncoder(w).Encode(jobResponse(job))
}

func (h *Handler) writeError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, ErrNotFound):
		writeProblem(w, http.StatusNotFound, "COLLECTION_JOB_NOT_FOUND", "収集対象または収集ジョブが見つかりません")
	case errors.Is(err, ErrConflict):
		writeProblem(w, http.StatusConflict, "COLLECTION_ALREADY_ACTIVE", "チャット収集はすでに開始されています")
	case errors.Is(err, ErrNotRetryable):
		writeProblem(w, http.StatusConflict, "COLLECTION_JOB_NOT_RETRYABLE", "この収集ジョブは再実行できません")
	default:
		writeProblem(w, http.StatusInternalServerError, "INTERNAL_ERROR", "収集ジョブを処理できませんでした")
	}
}

func writeProblem(w http.ResponseWriter, status int, code, title string) {
	w.Header().Set("Content-Type", "application/problem+json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]any{"type":"about:blank","title":title,"status":status,"code":code})
}

func jobResponse(value JobWithSteps) map[string]any {
	steps := make([]map[string]any, 0, len(value.Steps))
	for _, step := range value.Steps {
		steps = append(steps, map[string]any{"id":step.ID,"name":step.Name,"status":step.Status,"progressCount":step.ProgressCount,"errorCode":step.ErrorCode,"errorMessage":step.ErrorMessage,"startedAt":step.StartedAt,"finishedAt":step.FinishedAt})
	}
	return map[string]any{"id":value.ID,"streamId":value.StreamID,"kind":value.Kind,"status":value.Status,"attempt":value.Attempt,"retryOfJobId":value.RetryOfJobID,"progressCount":value.ProgressCount,"errorCode":value.ErrorCode,"errorMessage":value.ErrorMessage,"startedAt":value.StartedAt,"finishedAt":value.FinishedAt,"createdAt":value.CreatedAt,"updatedAt":value.UpdatedAt,"steps":steps}
}
