GRAPHIFY_BIN ?= graphify
GRAPHIFY_EXTRACT_ARGS ?= --code-only

.PHONY: setup dev dev-stop dev-logs db-up db-down api web test lint format check graphify graphify-update

setup:
	cd apps/web && npm install
	cd apps/api && go mod download

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

api:
	cd apps/api && go run ./cmd/api

web:
	cd apps/web && npm run dev

dev: db-up
	@set -eu; \
	trap 'kill 0' INT TERM EXIT; \
	(cd apps/api && go run ./cmd/api) & \
	(cd apps/web && npm run dev) & \
	wait

dev-stop:
	docker compose down

dev-logs:
	docker compose logs -f postgres

test:
	cd apps/api && go test ./...
	cd apps/web && npm test

lint:
	cd apps/api && gofmt -l . | tee /tmp/ysa-gofmt.txt; test ! -s /tmp/ysa-gofmt.txt
	cd apps/web && npm run typecheck

format:
	cd apps/api && gofmt -w .

check:
	@bash scripts/check-repository.sh
	cd apps/api && go test ./...
	cd apps/web && npm run typecheck && npm run build

graphify:
	@command -v "$(GRAPHIFY_BIN)" >/dev/null 2>&1 || { \
		echo "graphify is not installed; rebuild the Dev Container" >&2; \
		exit 1; \
	}
	"$(GRAPHIFY_BIN)" extract . $(GRAPHIFY_EXTRACT_ARGS)

graphify-update:
	@command -v "$(GRAPHIFY_BIN)" >/dev/null 2>&1 || { \
		echo "graphify is not installed; rebuild the Dev Container" >&2; \
		exit 1; \
	}
	@test -f graphify-out/graph.json || { \
		echo "graphify-out/graph.json does not exist; run 'make graphify' first" >&2; \
		exit 1; \
	}
	"$(GRAPHIFY_BIN)" update .
