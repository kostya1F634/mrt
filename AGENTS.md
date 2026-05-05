# Repository Guidelines

## Project Structure & Module Organization

This repository contains a compact Python desktop application. The main code lives in `main.py`; it handles mouse input capture, regression calculation, and the PyQt6 UI. Project metadata and dependencies are in `pyproject.toml`, with locked versions in `uv.lock`. `README.md` is present but empty. There is no `tests/` directory yet.

If the project grows, split UI widgets, input listeners, and calculation logic into modules under a package such as `mrt/`, and place tests under `tests/`.

## Build, Test, and Development Commands

Use `uv` for environment and dependency management.

```bash
make sync
```

Installs the Python version and dependencies.

```bash
make run
```

Runs the desktop application locally.

```bash
make test
```

Runs the current unit test suite.

Use `make help` to list all shortcuts, including `make r` and `make t`.

On Linux, mouse capture uses `evdev` and may require input-device permissions. The app reports the required group command when permissions are missing.

## Coding Style & Naming Conventions

Follow standard Python style: 4-space indentation, `snake_case` for functions and variables, and `PascalCase` for classes such as `MouseListenerThread` and `PlotWidget`. Keep constants in uppercase, as with `RAZER_GREEN` and `BG_COLOR`.

Prefer separating pure logic from UI code. Keep helpers like `calculate_regression()` side-effect free so they are easy to test. Existing comments and UI strings are in Russian; keep user-facing language consistent unless doing a deliberate localization pass.

## Testing Guidelines

Unit tests live under `tests/` and use Python's built-in `unittest` framework. Start with pure functions, especially `calculate_regression()`, under files named `test_*.py`. Cover edge cases such as empty paths, vertical movement, noisy horizontal movement, and simple diagonal paths.

For UI and device-input behavior, prefer small integration tests around extracted logic instead of tests that require real mouse hardware.

## Commit & Pull Request Guidelines

This repository has no commit history yet, so no local convention is established. Use short imperative commit subjects, for example `Add regression tests` or `Split input listener module`.

Pull requests should include a concise description, verification commands, and screenshots or recordings for visible UI changes. Link related issues when available. Note platform-specific behavior, especially Linux input permissions or Windows listener changes.

## Agent-Specific Instructions

Keep edits small and consistent with the current single-file structure unless the requested change justifies refactoring. Do not introduce new frameworks or formatting tools without updating `pyproject.toml` and documenting the matching command here.
