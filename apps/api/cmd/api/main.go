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

	chatapi "github.com/tsumasaki-kurageya/youtube-stream-analyzer/apps/api/internal/chat"
	collectionapi "github.com/tsumasaki-kurageya/youtube-stream-analyzer/apps/api/internal/collection"
	"github.com/tsumasaki-kurageya/youtube-stream-analyzer/apps/api/internal/platform"
	reservationapi "github.com/tsumasaki-kurageya/youtube-stream-analyzer/apps/api/internal/reservation"
	searchapi "github.com/tsumasaki-kurageya/youtube-stream-analyzer/apps/api/internal/search"
	streamapi "github.com/tsumasaki-kurageya/youtube-stream-analyzer/apps/api/internal/stream"
	transcriptapi "github.com/tsumasaki-kurageya/youtube-stream-analyzer/apps/api/internal/transcript"
	"github.com/tsumasaki-kurageya/youtube-stream-analyzer/apps/api/internal/youtube"
)

type healthResponse struct {
	Status string `json:"status"`
}

func main() {
	addr := os.Getenv("YSA_API_ADDRESS")
	if addr == "" {
		if port := os.Getenv("PORT"); port != "" {
			addr = ":" + port
		} else {
			addr = ":8080"
		}
	}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	db, err := platform.OpenDatabase(ctx, os.Getenv("YSA_DATABASE_URL"))
	if err != nil {
		log.Fatal(err)
	}
	defer db.Close()
	youtubeClient, err := youtube.NewClient(
		os.Getenv("YSA_YOUTUBE_API_KEY"),
		os.Getenv("YSA_YOUTUBE_API_BASE_URL"),
		10*time.Second,
	)
	if err != nil {
		log.Fatal(err)
	}
	streamRepository := streamapi.NewRepository(db)
	readHandler := streamapi.NewReadHandler(streamRepository)
	collectionHandler := collectionapi.NewHandler(collectionapi.NewRepository(db))
	chatHandler := chatapi.NewHandler(chatapi.NewRepository(db))
	transcriptHandler := transcriptapi.NewHandler(transcriptapi.NewRepository(db))
	searchHandler := searchapi.NewHandler(searchapi.NewRepository(db))
	reservationHandler := reservationapi.NewHandler(
		youtubeClient,
		reservationapi.NewRepository(db),
	)

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
	mux.Handle("POST /api/streams", streamapi.NewRegisterHandler(youtubeClient, streamRepository))
	mux.HandleFunc("GET /api/streams", readHandler.List)
	mux.HandleFunc("GET /api/streams/{streamId}", readHandler.Detail)
	mux.HandleFunc("POST /api/streams/{streamId}/collections", collectionHandler.StartFull)
	mux.HandleFunc("GET /api/streams/{streamId}/collections/latest", collectionHandler.Latest)
	mux.HandleFunc("POST /api/streams/{streamId}/chat-collections", collectionHandler.Start)
	mux.HandleFunc("GET /api/streams/{streamId}/chat-collections/latest", collectionHandler.Latest)
	mux.HandleFunc("POST /api/collection-jobs/{jobId}/retry", collectionHandler.Retry)
	mux.HandleFunc(
		"POST /api/collection-jobs/{jobId}/steps/{stepName}/retry",
		collectionHandler.RetryStep,
	)
	mux.HandleFunc("GET /api/streams/{streamId}/chat-messages", chatHandler.List)
	mux.HandleFunc(
		"GET /api/streams/{streamId}/transcript-segments",
		transcriptHandler.List,
	)
	mux.HandleFunc("GET /api/streams/{streamId}/search", searchHandler.Search)
	mux.HandleFunc("POST /api/reservations", reservationHandler.Create)
	mux.HandleFunc("GET /api/reservations", reservationHandler.List)
	mux.HandleFunc("GET /api/reservations/{reservationId}", reservationHandler.Detail)
	mux.HandleFunc("POST /api/reservations/{reservationId}/cancel", reservationHandler.Cancel)

	server := &http.Server{
		Addr:              addr,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}
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
