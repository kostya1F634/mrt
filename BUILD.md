# Building Desktop Binaries

This app uses Flet's `flet build` command to produce standalone desktop builds.

## Platform Rules

Flet desktop builds are platform-specific:

- Build Linux binaries on Linux or WSL.
- Build Windows binaries on Windows.
- Cross-building Windows binaries from Linux is not supported by Flet/Flutter.

## Linux

```bash
make sync
make build-linux
```

The output is written to `dist/linux`.

The project is pinned to Python `>=3.12,<3.13` because Flet 0.84 embeds Python 3.12 for Linux desktop builds. Building from a Python 3.14 virtualenv can break `serious_python` packaging and make CMake try to copy `/` into the bundle.

On some rolling Linux distributions, such as Manjaro/Arch, Flutter's generated Linux runner may compile embedded Python headers with `-Werror`. If the build fails with `_POSIX_C_SOURCE macro redefined` or `_XOPEN_SOURCE macro redefined`, use the Makefile target above rather than invoking `flet build` directly. It sets:

```bash
CFLAGS=-Wno-error=macro-redefined
CXXFLAGS=-Wno-error=macro-redefined
```

This keeps the warning visible but prevents it from failing the build.

Linux mouse capture uses `evdev`, so users may need input-device permissions:

```bash
sudo usermod -aG input $USER
```

Then log out and back in.

## Windows

Run this on Windows:

```powershell
uv sync
make build-windows
```

The output is written to `dist/windows`.

Windows app icons are taken from `assets/icon_windows.png` (or `assets/icon_windows.ico` if you provide one). The Makefile uses `--clear-cache` for Windows builds so Flet does not reuse an old default icon from `build/flutter`.

Windows builds require Visual Studio with the Desktop development with C++ workload. Developer Mode may also be required because Flutter uses symlinks during builds.

## Notes

`make build-matrix` prints the Flet platform matrix. In this Flet version it may exit non-zero if unrelated Flutter doctor checks fail, for example Android SDK checks; desktop Linux/Windows builds can still be available.

Build outputs are intentionally ignored by Git via `dist/`.
