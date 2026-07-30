GRAPHIFY_BIN ?= graphify
GRAPHIFY_EXTRACT_ARGS ?= --code-only

.PHONY: setup dev test lint format check graphify graphify-update

setup:
	@echo "M0 setup: no application dependencies yet"

# Application processes will be added from M1 onward.
dev:
	@echo "No application runtime is defined in M0"

test:
	@bash scripts/check-repository.sh

lint:
	@bash scripts/check-repository.sh

format:
	@echo "No formatter-managed application sources exist in M0"

check:
	@bash scripts/check-repository.sh

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
