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
	if err != nil {
		h.writeError(w, err)
		return
	}
	writeAcceptedJob(w, job)
}

func (h *Handler) StartFull(w http.ResponseWriter, r *http.Request) {
	job, err := h.repository.CreateFull(r.Context(), r.PathValue("streamId"))
	if err != nil {
		h.writeError(w, err)
		return
	}
	writeAcceptedJob(w, job)
}

func (h *Handler) Latest(w http.ResponseWriter, r *http.Request) {
	job, err := h.repository.Latest(r.Context(), r.PathValue("streamId"))
	if err != nil {
		h.writeError(w, err)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(jobResponse(job))
}

func (h *Handler) Retry(w http.ResponseWriter, r *http.Request) {
	job, err := h.repository.Retry(r.Context(), r.PathValue("jobId"))
	if err != nil {
		h.writeError(w, err)
		return
	}
	writeAcceptedJob(w, job)
}

func (h *Handler) RetryStep(w http.ResponseWriter, r *http.Request) {
	step, err := h.repository.RetryStep(
		r.Context(),
		r.PathValue("jobId"),
		r.PathValue("stepName"),
	)
	if err != nil {
		h.writeError(w, err)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusAccepted)
	_ = json.NewEncoder(w).Encode(stepResponse(step))
}

func writeAcceptedJob(w http.ResponseWriter, job JobWithSteps) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Location", "/api/collection-jobs/"+job.ID)
	w.WriteHeader(http.StatusAccepted)
	_ = json.NewEncoder(w).Encode(jobResponse(job))
}

func (h *Handler) writeError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, ErrNotFound):
		writeProblem(
			w,
			http.StatusNotFound,
			"COLLECTION_JOB_NOT_FOUND",
			"収集対象、収集ジョブ、または工程が見つかりません",
		)
	case errors.Is(err, ErrConflict):
		writeProblem(
			w,
			http.StatusConflict,
			"COLLECTION_ALREADY_ACTIVE",
			"この配信の収集はすでに開始されています",
		)
	case errors.Is(err, ErrNotRetryable):
		writeProblem(
			w,
			http.StatusConflict,
			"COLLECTION_STEP_NOT_RETRYABLE",
			"この収集工程は再実行できません",
		)
	default:
		writeProblem(
			w,
			http.StatusInternalServerError,
			"INTERNAL_ERROR",
			"収集ジョブを処理できませんでした",
		)
	}
}

func writeProblem(w http.ResponseWriter, status int, code, title string) {
	w.Header().Set("Content-Type", "application/problem+json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"type": "about:blank", "title": title, "status": status, "code": code,
	})
}

func jobResponse(value JobWithSteps) map[string]any {
	steps := make([]map[string]any, 0, len(value.Steps))
	for _, step := range value.Steps {
		steps = append(steps, stepResponse(step))
	}
	return map[string]any{
		"id": value.ID,
		"streamId": value.StreamID,
		"kind": value.Kind,
		"status": value.Status,
		"attempt": value.Attempt,
		"retryOfJobId": value.RetryOfJobID,
		"requestedSteps": value.RequestedSteps,
		"progressCount": value.ProgressCount,
		"errorCode": value.ErrorCode,
		"errorMessage": value.ErrorMessage,
		"startedAt": value.StartedAt,
		"finishedAt": value.FinishedAt,
		"createdAt": value.CreatedAt,
		"updatedAt": value.UpdatedAt,
		"steps": steps,
	}
}

func stepResponse(step Step) map[string]any {
	return map[string]any{
		"id": step.ID,
		"jobId": step.JobID,
		"name": step.Name,
		"status": step.Status,
		"attempt": step.Attempt,
		"progressCount": step.ProgressCount,
		"errorCode": step.ErrorCode,
		"errorMessage": step.ErrorMessage,
		"retryable": step.Retryable,
		"startedAt": step.StartedAt,
		"finishedAt": step.FinishedAt,
	}
}
