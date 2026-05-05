.PHONY: help sync run test check

UV_CACHE_DIR ?= .uv-cache
export UV_CACHE_DIR

help: ## Show available commands.
	@awk 'BEGIN {FS = ":.*## "; printf "Available commands:\n"} /^[a-zA-Z_-]+:.*## / {printf "  %-10s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync: ## Install dependencies with uv.
	uv sync

run: ## Run the Flet desktop application.
	uv run python main.py

test: ## Run unit tests.
	uv run python -m unittest discover -s tests

check: ## Compile Python files and run tests.
	uv run python -m py_compile main.py mrt_app/*.py archive/pyqt_main.py tests/test_regression.py
	uv run python -m unittest discover -s tests

r: run ## Alias for run.

t: test ## Alias for test.
