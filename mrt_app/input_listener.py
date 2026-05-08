import logging
import platform
import threading
import time

from mrt_app.diagnostics import analyze_measurement
from mrt_app.geometry import apply_motion_delta, calculate_path_quality, calculate_regression, quality_score_from_meta
from mrt_app.models import Measurement, MeasurementMeta


class MouseInputRecorder:
    def __init__(self, on_status=None):
        self.on_status = on_status or (lambda message, color="white": None)
        self.os_type = platform.system()
        self.recording = False
        self.filter_enabled = False
        self.path = [(0, 0)]
        self.timestamps = [0.0]
        self.cur_x = 0.0
        self.cur_y = 0.0
        self.frame_dx = 0.0
        self.frame_dy = 0.0
        self.accepted_delta_count = 0
        self.rejected_delta_count = 0
        self.recording_started_at = 0.0
        self._thread = None
        self._lock = threading.Lock()

    def start_listener(self):
        if self._thread and self._thread.is_alive():
            return

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        if self.os_type == "Linux":
            self._run_linux()
        elif self.os_type == "Windows":
            self._run_windows()
        else:
            self.on_status(f"ОС {self.os_type} не поддерживается", "#ff5555")

    def _run_linux(self):
        try:
            import evdev
        except ImportError:
            self.on_status("Установите evdev: uv add evdev", "#ff5555")
            return

        mouse = None
        for path in evdev.list_devices():
            try:
                device = evdev.InputDevice(path)
                caps = device.capabilities()
                rel_caps = caps.get(evdev.ecodes.EV_REL, [])
                key_caps = caps.get(evdev.ecodes.EV_KEY, [])
                if evdev.ecodes.REL_X in rel_caps and evdev.ecodes.BTN_LEFT in key_caps:
                    mouse = device
                    logging.info("Найдено устройство мыши: %s (%s)", device.name, path)
                    break
            except PermissionError:
                pass

        if not mouse:
            self.on_status("Нет прав к мыши: sudo usermod -aG input $USER, затем перезайдите.", "#ff5555")
            return

        self.on_status(f"Подключено: {mouse.name}", "#aaaaaa")
        try:
            for event in mouse.read_loop():
                if event.type == evdev.ecodes.EV_REL:
                    if event.code == evdev.ecodes.REL_X:
                        self.frame_dx += event.value
                    elif event.code == evdev.ecodes.REL_Y:
                        self.frame_dy -= event.value
                elif event.type == evdev.ecodes.EV_SYN:
                    if self.recording:
                        self.add_motion_delta(self.frame_dx, self.frame_dy, time.perf_counter())
                    self.frame_dx = 0.0
                    self.frame_dy = 0.0
        except Exception as exc:
            logging.exception("Ошибка чтения мыши")
            self.on_status(f"Ошибка чтения мыши: {exc}", "#ff5555")

    def _run_windows(self):
        try:
            from pynput import mouse
        except ImportError:
            self.on_status("Установите pynput: uv add pynput", "#ff5555")
            return

        self.on_status("Слушатель Windows запущен.", "#aaaaaa")
        last_abs = {"x": None, "y": None}

        def on_move(x, y):
            if not self.recording:
                last_abs["x"] = x
                last_abs["y"] = y
                return

            if last_abs["x"] is not None and last_abs["y"] is not None:
                dx = x - last_abs["x"]
                dy = y - last_abs["y"]
                self.add_motion_delta(dx, -dy, time.perf_counter())
            last_abs["x"] = x
            last_abs["y"] = y

        with mouse.Listener(on_move=on_move) as listener:
            listener.join()

    def start_recording(self):
        with self._lock:
            self.recording = True
            self.path = [(0, 0)]
            self.timestamps = [0.0]
            self.cur_x = 0.0
            self.cur_y = 0.0
            self.frame_dx = 0.0
            self.frame_dy = 0.0
            self.accepted_delta_count = 0
            self.rejected_delta_count = 0
            self.recording_started_at = time.perf_counter()

    def add_motion_delta(self, dx, dy, event_time=None):
        if dx == 0 and dy == 0:
            return

        with self._lock:
            self.path, accepted = apply_motion_delta(self.path, dx, dy, self.filter_enabled)
            if accepted:
                self.cur_x, self.cur_y = self.path[-1]
                event_time = event_time or time.perf_counter()
                self.timestamps.append(max(0.0, event_time - self.recording_started_at))
                self.accepted_delta_count += 1
            else:
                self.rejected_delta_count += 1

    def stop_recording(self):
        with self._lock:
            self.recording = False
            path = list(self.path)
            timestamps = list(self.timestamps)
            accepted = self.accepted_delta_count
            rejected = self.rejected_delta_count

        total = accepted + rejected
        rejected_ratio = rejected / total if total else 0.0
        quality = calculate_path_quality(path)
        path_length = sum(
            ((path[index][0] - path[index - 1][0]) ** 2 + (path[index][1] - path[index - 1][1]) ** 2) ** 0.5
            for index in range(1, len(path))
        )
        duration_seconds = timestamps[-1] if timestamps else 0.0
        meta = MeasurementMeta(
            accepted_delta_count=accepted,
            rejected_delta_count=rejected,
            rejected_ratio=rejected_ratio,
            rmse_ratio=quality["rmse_ratio"],
            path_length=path_length,
            duration_seconds=duration_seconds,
        )
        angle, slope, intercept = calculate_regression(path)
        quality_score, quality_label = quality_score_from_meta(meta, path)
        diagnostics = analyze_measurement(path, timestamps, meta)
        return Measurement(
            angle=angle,
            slope=slope,
            intercept=intercept,
            path=path,
            timestamps=timestamps,
            meta=meta,
            quality_score=quality_score,
            quality_label=quality_label,
            diagnostics=diagnostics,
        )

    def set_filter_enabled(self, enabled):
        self.filter_enabled = enabled
