package main

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	streamapi "github.com/tsumasaki-kurageya/youtube-stream-analyzer/apps/api/internal/stream"
	"github.com/tsumasaki-kurageya/youtube-stream-analyzer/apps/api/internal/platform"
	"github.com/tsumasaki-kurageya/youtube-stream-analyzer/apps/api/internal/youtube"
)

type healthResponse struct {
	Status string `json:"status"`
}

func main() {
	addr := os.Getenv("YSA_API_ADDRESS")
	if addr == "" {
		addr = ":8080"
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	db, err := platform.OpenDatabase(ctx, os.Getenv("YSA_DATABASE_URL"))
	if err != nil {
		log.Fatal(err)
	}
	defer db.Close()

	youtubeClient, err := youtube.NewClient(os.Getenv("YSA_YOUTUBE_API_KEY"), os.Getenv("YSA_YOUTUBE_API_BASE_URL"), 10*time.Second)
	if err != nil {
		log.Fatal(err)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/health", writeOK)
	mux.HandleFunc("GET /api/ready", func(w http.ResponseWriter, r *http.Request) {
		pingCtx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
		defer cancel()
		if err := db.Ping(pingCtx); err != nil {
			http.Error(w, "database unavailable", http.StatusServiceUnavailable)
			return
		}
		writeOK(w, r)
	})
	mux.Handle("POST /api/streams/preview", streamapi.NewPreviewHandler(youtubeClient))

	server := &http.Server{Addr: addr, Handler: mux, ReadHeaderTimeout: 5 * time.Second}
	go func() {
		log.Printf("Main API listening on %s", addr)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatal(err)
		}
	}()

	<-ctx.Done()
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Printf("shutdown failed: %v", err)
	}
}

func writeOK(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(healthResponse{Status: "ok"})
}
