.PHONY: help sync run run-linux-bin run-windows-bin test check build-linux build-windows build-matrix

UV_CACHE_DIR ?= .uv-cache
BUILD_DIR ?= dist
LINUX_BIN ?= $(BUILD_DIR)/linux/mouse-rotation-calibrator
WINDOWS_BIN ?= $(BUILD_DIR)/windows/mouse-rotation-calibrator.exe
FLET_PROJECT ?= mouse-rotation-calibrator
FLET_PRODUCT ?= Mouse Rotation Tuner
FLET_ORG ?= com.local
FLET_BUILD_COMMON = --project "$(FLET_PROJECT)" --product "$(FLET_PRODUCT)" --description "Mouse rotation calibration tool" --org "$(FLET_ORG)" --exclude archive --exclude tests --exclude .git --exclude .venv --exclude .uv-cache
LINUX_BUILD_CFLAGS ?= -Wno-error=macro-redefined
export UV_CACHE_DIR

help: ## Show available commands.
	@awk 'BEGIN {FS = ":.*## "; printf "Available commands:\n"} /^[a-zA-Z_-]+:.*## / {printf "  %-10s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

sync: ## Install dependencies with uv.
	uv sync

run: ## Run the Flet desktop application.
	uv run python main.py

run-linux-bin: ## Run compiled Linux binary from dist/linux.
	"$(LINUX_BIN)"

run-windows-bin: ## Run compiled Windows binary from dist/windows; run on Windows only.
	"$(WINDOWS_BIN)"

test: ## Run unit tests.
	uv run python -m unittest discover -s tests

check: ## Compile Python files and run tests.
	uv run python -m py_compile main.py mrt_app/*.py archive/pyqt_main.py tests/test_regression.py
	uv run python -m unittest discover -s tests

build-linux: check ## Build Linux desktop binary into dist/linux.
	CFLAGS="$(LINUX_BUILD_CFLAGS)" CXXFLAGS="$(LINUX_BUILD_CFLAGS)" uv run flet build linux . --output "$(BUILD_DIR)/linux" $(FLET_BUILD_COMMON)

build-windows: check ## Build Windows desktop binary into dist/windows; run on Windows only.
	uv run flet build windows . --output "$(BUILD_DIR)/windows" $(FLET_BUILD_COMMON)

build-matrix: ## Show Flet platform build matrix.
	-uv run flet build linux --show-platform-matrix --skip-flutter-doctor

r: run ## Alias for run.

t: test ## Alias for test.
