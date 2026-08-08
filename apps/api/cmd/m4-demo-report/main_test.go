package main

import (
	"strings"
	"testing"
	"time"
)

func TestEvaluateCompleteRealDataDemo(t *testing.T) {
	report := completeFixture()
	criteria, complete := evaluate(report, true)
	if !complete {
		t.Fatalf("expected complete report, criteria=%+v", criteria)
	}
	for _, item := range criteria {
		if !item.Passed {
			t.Errorf("expected %q to pass: %s", item.Name, item.Detail)
		}
	}
}

func TestEvaluateRejectsDuplicateJobsAndMissingManualChecks(t *testing.T) {
	report := completeFixture()
	report.CollectionJobCount = 2
	report.Manual.M3Search = false
	criteria, complete := evaluate(report, true)
	if complete {
		t.Fatal("expected incomplete report")
	}
	failed := map[string]bool{}
	for _, item := range criteria {
		if !item.Passed {
			failed[item.Name] = true
		}
	}
	if !failed["CollectionJobが重複していない"] {
		t.Error("duplicate job criterion did not fail")
	}
	if !failed["M3検索を確認"] {
		t.Error("manual search criterion did not fail")
	}
}

func TestEvaluateCanRecordTranscriptNoDataDemo(t *testing.T) {
	report := completeFixture()
	report.TranscriptCount = 0
	_, complete := evaluate(report, false)
	if !complete {
		t.Fatal("transcript should be optional when requireTranscript is false")
	}
}

func TestRenderMarkdownContainsOnlyRedactedEvidence(t *testing.T) {
	report := completeFixture()
	report.GeneratedAt = time.Date(2026, 8, 3, 7, 30, 0, 0, time.UTC)
	report.Criteria, report.Complete = evaluate(report, true)
	markdown := renderMarkdown(report)
	for _, expected := range []string{
		"# M4 実配信完了デモ結果",
		"判定: **PASS**",
		"video123456",
		"チャット保存件数: **42**",
		"字幕保存件数: **12**",
		"Cookie、APIキー、チャット本文、字幕本文を含めていません",
	} {
		if !strings.Contains(markdown, expected) {
			t.Errorf("markdown does not contain %q", expected)
		}
	}
	for _, forbidden := range []string{"AIza", "youtube.com/watch", "sample chat body"} {
		if strings.Contains(markdown, forbidden) {
			t.Errorf("markdown contains forbidden value %q", forbidden)
		}
	}
}

func completeFixture() demoReport {
	streamID := "00000000-0000-0000-0000-000000000001"
	jobID := "00000000-0000-0000-0000-000000000002"
	status := "succeeded"
	created := time.Date(2026, 8, 3, 1, 0, 0, 0, time.UTC)
	live := "scheduled"
	waiting := "live"
	collecting := "waiting_for_archive"
	completed := "collecting"
	return demoReport{
		ReservationID:      "00000000-0000-0000-0000-000000000003",
		YouTubeVideoID:     "video123456",
		ReservationState:   "completed",
		ReservationCreated: created,
		ReservationUpdated: created.Add(2 * time.Hour),
		StreamID:           &streamID,
		CollectionJobID:    &jobID,
		CollectionStatus:   &status,
		CollectionJobCount: 1,
		ChatMessageCount:   42,
		TranscriptCount:    12,
		Transitions: []transition{
			{ToState: "scheduled", ReasonCode: "reservation_created", CreatedAt: created},
			{FromState: &live, ToState: "live", ReasonCode: "stream_live", CreatedAt: created.Add(30 * time.Minute)},
			{FromState: &waiting, ToState: "waiting_for_archive", ReasonCode: "stream_ended", CreatedAt: created.Add(time.Hour)},
			{FromState: &collecting, ToState: "collecting", ReasonCode: "collection_started", CreatedAt: created.Add(70 * time.Minute)},
			{FromState: &completed, ToState: "completed", ReasonCode: "collection_succeeded", CreatedAt: created.Add(90 * time.Minute)},
		},
		Steps: []collectionStep{
			{Name: "metadata", Status: "succeeded", Attempt: 1},
			{Name: "chat_replay", Status: "succeeded", Attempt: 1, ProgressCount: 42},
			{Name: "transcript", Status: "succeeded", Attempt: 1, ProgressCount: 12},
		},
		Manual: manualConfirmations{
			WorkerRestart: true,
			M3Sync:        true,
			M3Search:      true,
			M3Seek:        true,
		},
	}
}
