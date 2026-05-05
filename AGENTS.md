# Repository Guidelines

## Project Structure & Module Organization

This repository contains a Python desktop mouse-rotation calibration tool. `main.py` is the Flet entrypoint. Application code lives in `mrt_app/`: `flet_ui.py` builds the UI, `input_listener.py` handles Linux/Windows mouse input, `geometry.py` contains testable math and filtering logic, and `models.py` defines shared dataclasses. The previous PyQt implementation is archived in `archive/pyqt_main.py`.

Unit tests live in `tests/`. Project metadata and dependencies are in `pyproject.toml`, with locked versions in `uv.lock`.

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

Follow standard Python style: 4-space indentation, `snake_case` for functions and variables, and `PascalCase` for classes such as `MouseRotationApp` and `MouseInputRecorder`. Keep constants in uppercase, as with `RAZER_GREEN` and `BG_COLOR`.

Keep pure logic out of the UI layer. Helpers like `calculate_regression()` and `apply_motion_delta()` should remain side-effect free. Existing UI strings are in Russian; keep user-facing language consistent unless doing a deliberate localization pass.

## Testing Guidelines

Unit tests live under `tests/` and use Python's built-in `unittest` framework. Start with pure functions, especially `calculate_regression()`, under files named `test_*.py`. Cover edge cases such as empty paths, vertical movement, noisy horizontal movement, and simple diagonal paths.

For UI and device-input behavior, prefer small integration tests around extracted logic instead of tests that require real mouse hardware.

## Commit & Pull Request Guidelines

Use short imperative commit subjects, for example `Add regression tests` or `Refactor Flet input listener`.

Pull requests should include a concise description, verification commands, and screenshots or recordings for visible UI changes. Link related issues when available. Note platform-specific behavior, especially Linux input permissions or Windows listener changes.

## Agent-Specific Instructions

Keep UI, input, math, and data-model changes in their respective modules. Do not introduce new frameworks or formatting tools without updating `pyproject.toml` and documenting the matching command here.
