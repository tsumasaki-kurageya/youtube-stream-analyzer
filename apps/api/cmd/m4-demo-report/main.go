package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type transition struct {
	FromState  *string   `json:"fromState,omitempty"`
	ToState    string    `json:"toState"`
	ReasonCode string    `json:"reasonCode"`
	CreatedAt  time.Time `json:"createdAt"`
}

type collectionStep struct {
	Name          string  `json:"name"`
	Status        string  `json:"status"`
	Attempt       int     `json:"attempt"`
	ProgressCount int64   `json:"progressCount"`
	ErrorCode     *string `json:"errorCode,omitempty"`
}

type manualConfirmations struct {
	WorkerRestart bool `json:"workerRestart"`
	M3Sync        bool `json:"m3Sync"`
	M3Search      bool `json:"m3Search"`
	M3Seek        bool `json:"m3Seek"`
}

type criterion struct {
	Name   string `json:"name"`
	Passed bool   `json:"passed"`
	Detail string `json:"detail"`
}

type demoReport struct {
	GeneratedAt        time.Time           `json:"generatedAt"`
	ReservationID      string              `json:"reservationId"`
	YouTubeVideoID     string              `json:"youtubeVideoId"`
	ReservationState   string              `json:"reservationState"`
	ScheduledStartAt   *time.Time          `json:"scheduledStartAt,omitempty"`
	ActualStartAt      *time.Time          `json:"actualStartAt,omitempty"`
	ActualEndAt        *time.Time          `json:"actualEndAt,omitempty"`
	ReservationCreated time.Time           `json:"reservationCreatedAt"`
	ReservationUpdated time.Time           `json:"reservationUpdatedAt"`
	CompletedAt        *time.Time          `json:"completedAt,omitempty"`
	StreamID           *string             `json:"streamId,omitempty"`
	CollectionJobID    *string             `json:"collectionJobId,omitempty"`
	CollectionStatus   *string             `json:"collectionStatus,omitempty"`
	CollectionCreated  *time.Time          `json:"collectionCreatedAt,omitempty"`
	CollectionStarted  *time.Time          `json:"collectionStartedAt,omitempty"`
	CollectionFinished *time.Time          `json:"collectionFinishedAt,omitempty"`
	CollectionJobCount int64               `json:"collectionJobCount"`
	ChatMessageCount   int64               `json:"chatMessageCount"`
	TranscriptCount    int64               `json:"transcriptSegmentCount"`
	Transitions        []transition        `json:"transitions"`
	Steps              []collectionStep    `json:"steps"`
	Manual             manualConfirmations `json:"manualConfirmations"`
	Criteria           []criterion         `json:"criteria"`
	Complete           bool                `json:"complete"`
}

type commandOptions struct {
	DatabaseURL          string
	ReservationID        string
	Format               string
	Output               string
	Strict               bool
	RequireTranscript    bool
	WorkerRestart        bool
	M3Sync               bool
	M3Search             bool
	M3Seek               bool
}

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr io.Writer) int {
	options, err := parseOptions(args, stderr)
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 2
	}

	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	pool, err := pgxpool.New(ctx, options.DatabaseURL)
	if err != nil {
		fmt.Fprintf(stderr, "connect database: %v\n", err)
		return 1
	}
	defer pool.Close()

	report, err := loadReport(ctx, pool, options.ReservationID)
	if err != nil {
		fmt.Fprintf(stderr, "load demo evidence: %v\n", err)
		return 1
	}
	report.GeneratedAt = time.Now().UTC()
	report.Manual = manualConfirmations{
		WorkerRestart: options.WorkerRestart,
		M3Sync:        options.M3Sync,
		M3Search:      options.M3Search,
		M3Seek:        options.M3Seek,
	}
	report.Criteria, report.Complete = evaluate(report, options.RequireTranscript)

	var content []byte
	switch options.Format {
	case "markdown":
		content = []byte(renderMarkdown(report))
	case "json":
		content, err = json.MarshalIndent(report, "", "  ")
		if err == nil {
			content = append(content, '\n')
		}
	default:
		err = fmt.Errorf("unsupported format %q", options.Format)
	}
	if err != nil {
		fmt.Fprintf(stderr, "render report: %v\n", err)
		return 1
	}

	if options.Output == "" {
		if _, err := stdout.Write(content); err != nil {
			fmt.Fprintf(stderr, "write report: %v\n", err)
			return 1
		}
	} else if err := os.WriteFile(options.Output, content, 0o600); err != nil {
		fmt.Fprintf(stderr, "write %s: %v\n", options.Output, err)
		return 1
	}

	if options.Strict && !report.Complete {
		return 3
	}
	return 0
}

func parseOptions(args []string, stderr io.Writer) (commandOptions, error) {
	var options commandOptions
	flags := flag.NewFlagSet("m4-demo-report", flag.ContinueOnError)
	flags.SetOutput(stderr)
	flags.StringVar(&options.DatabaseURL, "database-url", os.Getenv("YSA_DATABASE_URL"), "PostgreSQL connection URL")
	flags.StringVar(&options.ReservationID, "reservation-id", "", "M4 reservation UUID")
	flags.StringVar(&options.Format, "format", "markdown", "output format: markdown or json")
	flags.StringVar(&options.Output, "output", "", "output file; stdout when omitted")
	flags.BoolVar(&options.Strict, "strict", false, "return a non-zero exit code when completion criteria are not met")
	flags.BoolVar(&options.RequireTranscript, "require-transcript", true, "require at least one saved transcript segment")
	flags.BoolVar(&options.WorkerRestart, "worker-restart-confirmed", false, "confirm that the monitor worker was restarted during the demo")
	flags.BoolVar(&options.M3Sync, "m3-sync-confirmed", false, "confirm synchronized player/chat/transcript display")
	flags.BoolVar(&options.M3Search, "m3-search-confirmed", false, "confirm M3 text search with real data")
	flags.BoolVar(&options.M3Seek, "m3-seek-confirmed", false, "confirm timestamp jump from a real search or timeline item")
	if err := flags.Parse(args); err != nil {
		return commandOptions{}, err
	}
	if strings.TrimSpace(options.DatabaseURL) == "" {
		return commandOptions{}, errors.New("YSA_DATABASE_URL or -database-url is required")
	}
	if strings.TrimSpace(options.ReservationID) == "" {
		return commandOptions{}, errors.New("-reservation-id is required")
	}
	if options.Format != "markdown" && options.Format != "json" {
		return commandOptions{}, errors.New("-format must be markdown or json")
	}
	return options, nil
}

func loadReport(ctx context.Context, pool *pgxpool.Pool, reservationID string) (demoReport, error) {
	var report demoReport
	err := pool.QueryRow(ctx, `
		SELECT r.id::text,r.youtube_video_id,r.state,
		       r.scheduled_start_at,r.actual_start_at,r.actual_end_at,
		       r.created_at,r.updated_at,r.completed_at,
		       r.stream_id::text,r.collection_job_id::text,
		       j.status,j.created_at,j.started_at,j.finished_at
		FROM reservation.reservations r
		LEFT JOIN collection.collection_jobs j ON j.id=r.collection_job_id
		WHERE r.id=$1
	`, reservationID).Scan(
		&report.ReservationID,
		&report.YouTubeVideoID,
		&report.ReservationState,
		&report.ScheduledStartAt,
		&report.ActualStartAt,
		&report.ActualEndAt,
		&report.ReservationCreated,
		&report.ReservationUpdated,
		&report.CompletedAt,
		&report.StreamID,
		&report.CollectionJobID,
		&report.CollectionStatus,
		&report.CollectionCreated,
		&report.CollectionStarted,
		&report.CollectionFinished,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return demoReport{}, fmt.Errorf("reservation %s was not found", reservationID)
	}
	if err != nil {
		return demoReport{}, err
	}

	rows, err := pool.Query(ctx, `
		SELECT from_state,to_state,reason_code,created_at
		FROM reservation.reservation_transitions
		WHERE reservation_id=$1
		ORDER BY created_at,id
	`, reservationID)
	if err != nil {
		return demoReport{}, err
	}
	defer rows.Close()
	for rows.Next() {
		var item transition
		if err := rows.Scan(&item.FromState, &item.ToState, &item.ReasonCode, &item.CreatedAt); err != nil {
			return demoReport{}, err
		}
		report.Transitions = append(report.Transitions, item)
	}
	if err := rows.Err(); err != nil {
		return demoReport{}, err
	}

	if report.CollectionJobID != nil {
		stepRows, err := pool.Query(ctx, `
			SELECT name,status,attempt,progress_count,error_code
			FROM collection.collection_steps
			WHERE job_id=$1
			ORDER BY CASE name
			    WHEN 'metadata' THEN 1
			    WHEN 'chat_replay' THEN 2
			    WHEN 'transcript' THEN 3
			    ELSE 100 END,name
		`, *report.CollectionJobID)
		if err != nil {
			return demoReport{}, err
		}
		defer stepRows.Close()
		for stepRows.Next() {
			var item collectionStep
			if err := stepRows.Scan(&item.Name, &item.Status, &item.Attempt, &item.ProgressCount, &item.ErrorCode); err != nil {
				return demoReport{}, err
			}
			report.Steps = append(report.Steps, item)
		}
		if err := stepRows.Err(); err != nil {
			return demoReport{}, err
		}
	}

	if report.StreamID != nil {
		if err := pool.QueryRow(ctx,
			`SELECT count(*) FROM collection.collection_jobs WHERE stream_id=$1`,
			*report.StreamID,
		).Scan(&report.CollectionJobCount); err != nil {
			return demoReport{}, err
		}
		if err := pool.QueryRow(ctx,
			`SELECT count(*) FROM chat.chat_messages WHERE stream_id=$1`,
			*report.StreamID,
		).Scan(&report.ChatMessageCount); err != nil {
			return demoReport{}, err
		}
		if err := pool.QueryRow(ctx,
			`SELECT count(*) FROM transcript.transcript_segments WHERE stream_id=$1`,
			*report.StreamID,
		).Scan(&report.TranscriptCount); err != nil {
			return demoReport{}, err
		}
	}
	return report, nil
}

func evaluate(report demoReport, requireTranscript bool) ([]criterion, bool) {
	criteria := []criterion{
		check("予約が完了状態", report.ReservationState == "completed", report.ReservationState),
		check("自動収集ジョブが関連付け済み", report.StreamID != nil && report.CollectionJobID != nil, pointerPair(report.StreamID, report.CollectionJobID)),
		check("自動収集ジョブが成功", report.CollectionStatus != nil && *report.CollectionStatus == "succeeded", pointerValue(report.CollectionStatus)),
		check("配信中状態を記録", hasTransition(report.Transitions, "live"), transitionSummary(report.Transitions)),
		check("アーカイブ待ち状態を記録", hasTransition(report.Transitions, "waiting_for_archive"), transitionSummary(report.Transitions)),
		check("自動収集開始状態を記録", hasTransition(report.Transitions, "collecting"), transitionSummary(report.Transitions)),
		check("完了状態遷移を記録", hasTransition(report.Transitions, "completed"), transitionSummary(report.Transitions)),
		check("CollectionJobが重複していない", report.CollectionJobCount == 1, fmt.Sprintf("%d job(s)", report.CollectionJobCount)),
		check("チャットを保存", report.ChatMessageCount > 0, fmt.Sprintf("%d message(s)", report.ChatMessageCount)),
		check("監視プロセス再起動を確認", report.Manual.WorkerRestart, manualDetail(report.Manual.WorkerRestart)),
		check("M3同期表示を確認", report.Manual.M3Sync, manualDetail(report.Manual.M3Sync)),
		check("M3検索を確認", report.Manual.M3Search, manualDetail(report.Manual.M3Search)),
		check("M3時刻ジャンプを確認", report.Manual.M3Seek, manualDetail(report.Manual.M3Seek)),
	}
	if requireTranscript {
		criteria = append(criteria, check("字幕を保存", report.TranscriptCount > 0, fmt.Sprintf("%d segment(s)", report.TranscriptCount)))
	} else {
		criteria = append(criteria, check("字幕保存件数を記録", true, fmt.Sprintf("%d segment(s); transcript not required", report.TranscriptCount)))
	}
	complete := true
	for _, item := range criteria {
		if !item.Passed {
			complete = false
		}
	}
	return criteria, complete
}

func check(name string, passed bool, detail string) criterion {
	return criterion{Name: name, Passed: passed, Detail: detail}
}

func hasTransition(items []transition, state string) bool {
	for _, item := range items {
		if item.ToState == state {
			return true
		}
	}
	return false
}

func transitionSummary(items []transition) string {
	if len(items) == 0 {
		return "no transitions"
	}
	states := make([]string, 0, len(items))
	for _, item := range items {
		states = append(states, item.ToState)
	}
	return strings.Join(states, " -> ")
}

func pointerValue(value *string) string {
	if value == nil {
		return "not linked"
	}
	return *value
}

func pointerPair(first, second *string) string {
	return fmt.Sprintf("stream=%s, job=%s", pointerValue(first), pointerValue(second))
}

func manualDetail(value bool) string {
	if value {
		return "confirmed"
	}
	return "not confirmed"
}

func renderMarkdown(report demoReport) string {
	var builder strings.Builder
	builder.WriteString("# M4 実配信完了デモ結果\n\n")
	fmt.Fprintf(&builder, "- 判定: **%s**\n", passLabel(report.Complete))
	fmt.Fprintf(&builder, "- 生成時刻: %s\n", formatTime(&report.GeneratedAt))
	fmt.Fprintf(&builder, "- Reservation ID: `%s`\n", markdownCell(report.ReservationID))
	fmt.Fprintf(&builder, "- YouTube video ID: `%s`\n", markdownCell(report.YouTubeVideoID))
	fmt.Fprintf(&builder, "- Reservation state: `%s`\n", markdownCell(report.ReservationState))
	fmt.Fprintf(&builder, "- Stream ID: `%s`\n", markdownCell(pointerValue(report.StreamID)))
	fmt.Fprintf(&builder, "- CollectionJob ID: `%s`\n", markdownCell(pointerValue(report.CollectionJobID)))
	fmt.Fprintf(&builder, "- Collection status: `%s`\n\n", markdownCell(pointerValue(report.CollectionStatus)))

	builder.WriteString("## 時刻\n\n")
	builder.WriteString("| 項目 | 時刻 |\n|---|---|\n")
	fmt.Fprintf(&builder, "| 予約登録 | %s |\n", formatTime(&report.ReservationCreated))
	fmt.Fprintf(&builder, "| 配信予定 | %s |\n", formatTime(report.ScheduledStartAt))
	fmt.Fprintf(&builder, "| 配信開始 | %s |\n", formatTime(report.ActualStartAt))
	fmt.Fprintf(&builder, "| 配信終了 | %s |\n", formatTime(report.ActualEndAt))
	fmt.Fprintf(&builder, "| 収集開始 | %s |\n", formatTime(report.CollectionStarted))
	fmt.Fprintf(&builder, "| 収集終了 | %s |\n", formatTime(report.CollectionFinished))
	fmt.Fprintf(&builder, "| 予約完了 | %s |\n\n", formatTime(report.CompletedAt))

	builder.WriteString("## 状態遷移\n\n")
	builder.WriteString("| 時刻 | 遷移 | 理由 |\n|---|---|---|\n")
	for _, item := range report.Transitions {
		from := "—"
		if item.FromState != nil {
			from = *item.FromState
		}
		fmt.Fprintf(&builder, "| %s | `%s` → `%s` | `%s` |\n",
			formatTime(&item.CreatedAt), markdownCell(from), markdownCell(item.ToState), markdownCell(item.ReasonCode))
	}
	builder.WriteString("\n## 収集結果\n\n")
	fmt.Fprintf(&builder, "- CollectionJob件数: **%d**\n", report.CollectionJobCount)
	fmt.Fprintf(&builder, "- チャット保存件数: **%d**\n", report.ChatMessageCount)
	fmt.Fprintf(&builder, "- 字幕保存件数: **%d**\n\n", report.TranscriptCount)
	builder.WriteString("| 工程 | 状態 | Attempt | 件数 | エラーコード |\n|---|---|---:|---:|---|\n")
	for _, item := range report.Steps {
		fmt.Fprintf(&builder, "| `%s` | `%s` | %d | %d | `%s` |\n",
			markdownCell(item.Name), markdownCell(item.Status), item.Attempt, item.ProgressCount, markdownCell(pointerValue(item.ErrorCode)))
	}

	builder.WriteString("\n## 完了条件\n\n")
	builder.WriteString("| 判定 | 項目 | 証跡 |\n|---|---|---|\n")
	for _, item := range report.Criteria {
		mark := "❌"
		if item.Passed {
			mark = "✅"
		}
		fmt.Fprintf(&builder, "| %s | %s | %s |\n", mark, markdownCell(item.Name), markdownCell(item.Detail))
	}
	builder.WriteString("\nこのレポートにはCookie、APIキー、チャット本文、字幕本文を含めていません。\n")
	return builder.String()
}

func formatTime(value *time.Time) string {
	if value == nil || value.IsZero() {
		return "—"
	}
	return value.UTC().Format(time.RFC3339)
}

func passLabel(value bool) string {
	if value {
		return "PASS"
	}
	return "INCOMPLETE"
}

func markdownCell(value string) string {
	value = strings.ReplaceAll(value, "|", "\\|")
	value = strings.ReplaceAll(value, "\n", " ")
	return value
}
