package main

import (
	"database/sql"
	"log"
	"os"

	_ "github.com/jackc/pgx/v5/stdlib"
	"github.com/pressly/goose/v3"
)

func main() {
	databaseURL := os.Getenv("YSA_DATABASE_URL")
	if databaseURL == "" {
		log.Fatal("YSA_DATABASE_URL is required")
	}
	command := "up"
	if len(os.Args) > 1 {
		command = os.Args[1]
	}

	db, err := sql.Open("pgx", databaseURL)
	if err != nil {
		log.Fatal(err)
	}
	defer db.Close()

	if err := goose.Run(command, db, "../../database/migrations"); err != nil {
		log.Fatalf("goose %s: %v", command, err)
	}
}
