GRAPHIFY_BIN ?= graphify
GRAPHIFY_EXTRACT_ARGS ?= --code-only
VENV ?= $(CURDIR)/.venv
PYTHON ?= $(VENV)/bin/python
SYSTEM_PYTHON ?= python3
WITH_ENV := $(CURDIR)/scripts/with-env.sh

.PHONY: setup dev dev-stop dev-logs db-up db-down db-migrate db-rollback api web worker gateway worker-check gateway-check contracts-check deployment-check test lint format check graphify graphify-update

setup: $(VENV)/bin/python
	cd apps/web && npm install
	cd apps/api && go mod download
	cd apps/worker && $(PYTHON) -m pip install -e '.[dev]'
	cd apps/youtube-data-gateway && $(PYTHON) -m pip install -e '.[dev]'

$(VENV)/bin/python:
	$(SYSTEM_PYTHON) -m venv $(VENV)

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

db-migrate:
	$(WITH_ENV) bash -c 'cd apps/api && exec go run ./cmd/migrate up'

db-rollback:
	$(WITH_ENV) bash -c 'cd apps/api && exec go run ./cmd/migrate down'

api:
	$(WITH_ENV) bash -c 'cd apps/api && exec go run ./cmd/api'

web:
	$(WITH_ENV) bash -c 'cd apps/web && exec npm run dev'

worker:
	$(WITH_ENV) bash -c 'cd apps/worker && exec $(PYTHON) -m ysa_worker.main'

gateway:
	$(WITH_ENV) bash -c 'cd apps/youtube-data-gateway && exec $(PYTHON) -m ysa_gateway.app'

worker-check:
	cd apps/worker && $(PYTHON) -m ruff check . && $(PYTHON) -m mypy src tests && $(PYTHON) -m pytest

gateway-check:
	cd apps/youtube-data-gateway && $(PYTHON) -m ruff check . && $(PYTHON) -m mypy src tests && $(PYTHON) -m pytest

contracts-check:
	@set -eu; for contract in contracts/*.yaml; do $(PYTHON) -m openapi_spec_validator "$$contract"; done

deployment-check:
	@bash scripts/check-deployment.sh

dev: db-up db-migrate
	@flock -n -E 73 .dev.lock $(WITH_ENV) bash -c "set -eu; \
	trap 'kill 0' INT TERM EXIT; \
	(cd apps/api && go run ./cmd/api) & \
	(cd apps/web && npm run dev) & \
	(cd apps/youtube-data-gateway && $(PYTHON) -m ysa_gateway.app) & \
	(cd apps/worker && $(PYTHON) -m ysa_worker.main) & \
	wait" || { status=$$?; \
		if [ $$status -eq 73 ]; then \
			echo "Development services are already running."; \
		else \
			exit $$status; \
		fi; \
	}

dev-stop:
	docker compose down

dev-logs:
	docker compose logs -f postgres

test:
	cd apps/api && go test -p 1 ./...
	cd apps/web && npm test
	cd apps/worker && $(PYTHON) -m pytest
	cd apps/youtube-data-gateway && $(PYTHON) -m pytest

lint:
	cd apps/api && gofmt -l . | tee /tmp/ysa-gofmt.txt; test ! -s /tmp/ysa-gofmt.txt
	cd apps/web && npm run typecheck
	cd apps/worker && $(PYTHON) -m ruff check . && $(PYTHON) -m mypy src tests
	cd apps/youtube-data-gateway && $(PYTHON) -m ruff check . && $(PYTHON) -m mypy src tests

format:
	cd apps/api && gofmt -w .
	cd apps/worker && $(PYTHON) -m ruff format .
	cd apps/youtube-data-gateway && $(PYTHON) -m ruff format .

check:
	@bash scripts/check-repository.sh
	cd apps/api && go test -p 1 ./...
	cd apps/web && npm run typecheck && npm run build
	$(MAKE) worker-check
	$(MAKE) gateway-check
	$(MAKE) contracts-check

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
