.PHONY: setup dev test lint format check

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
