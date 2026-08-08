package collection

import (
	"testing"
	"time"
)

func TestStepResponseIncludesWorkerLiveness(t *testing.T) {
	heartbeatAt := time.Date(2026, 8, 8, 12, 0, 0, 0, time.UTC)
	leaseExpiresAt := heartbeatAt.Add(2 * time.Minute)

	response := stepResponse(Step{
		ID:             "step-id",
		HeartbeatAt:    &heartbeatAt,
		LeaseExpiresAt: &leaseExpiresAt,
	})

	if response["heartbeatAt"] != &heartbeatAt {
		t.Fatalf("heartbeatAt = %#v, want %s", response["heartbeatAt"], heartbeatAt)
	}
	if response["leaseExpiresAt"] != &leaseExpiresAt {
		t.Fatalf("leaseExpiresAt = %#v, want %s", response["leaseExpiresAt"], leaseExpiresAt)
	}
}
