GRAPHIFY_BIN ?= graphify
GRAPHIFY_EXTRACT_ARGS ?= --code-only
PYTHON ?= python3

.PHONY: setup dev dev-stop dev-logs db-up db-down db-migrate db-rollback api web worker worker-check test lint format check m4-demo-report graphify graphify-update

setup:
	cd apps/web && npm install
	cd apps/api && go mod download
	cd apps/worker && $(PYTHON) -m pip install -e '.[dev]'

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

db-migrate:
	cd apps/api && go run ./cmd/migrate up

db-rollback:
	cd apps/api && go run ./cmd/migrate down

api:
	cd apps/api && go run ./cmd/api

web:
	cd apps/web && npm run dev

worker:
	cd apps/worker && $(PYTHON) -m ysa_worker.main

worker-check:
	cd apps/worker && ruff check . && mypy src tests && pytest

dev: db-up db-migrate
	@set -eu; \
	trap 'kill 0' INT TERM EXIT; \
	(cd apps/api && go run ./cmd/api) & \
	(cd apps/web && npm run dev) & \
	(cd apps/worker && $(PYTHON) -m ysa_worker.main) & \
	wait

dev-stop:
	docker compose down

dev-logs:
	docker compose logs -f postgres

test:
	cd apps/api && go test -p 1 ./...
	cd apps/web && npm test
	cd apps/worker && pytest

lint:
	cd apps/api && gofmt -l . | tee /tmp/ysa-gofmt.txt; test ! -s /tmp/ysa-gofmt.txt
	cd apps/web && npm run typecheck
	cd apps/worker && ruff check . && mypy src tests

format:
	cd apps/api && gofmt -w .
	cd apps/worker && ruff format .

check:
	@bash scripts/check-repository.sh
	cd apps/api && go test -p 1 ./...
	cd apps/web && npm run typecheck && npm run build
	$(MAKE) worker-check

m4-demo-report:
	@test -n "$(RESERVATION_ID)" || { echo "RESERVATION_ID is required" >&2; exit 1; }
	cd apps/api && go run ./cmd/m4-demo-report -reservation-id "$(RESERVATION_ID)" $(M4_DEMO_FLAGS)

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
