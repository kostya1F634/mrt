import math

import flet as ft
import flet.canvas as cv

from mrt_app.geometry import summarize_series
from mrt_app.i18n import DEFAULT_LANGUAGE, translate
from mrt_app.input_listener import MouseInputRecorder
from mrt_app.theme import BG_COLOR, GRID_COLOR, MUTED_COLOR, PANEL_ALT_COLOR, PANEL_COLOR, RAZER_GREEN


DEFAULT_CANVAS_WIDTH = 900
DEFAULT_CANVAS_HEIGHT = 320


class MouseRotationApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.recorder = MouseInputRecorder(on_status=self.set_status)
        self.samples = []
        self.last_measurement = None
        self.series_collapsed = True
        self.recording = False
        self.filter_enabled = False
        self.language = DEFAULT_LANGUAGE
        self.canvas_width = DEFAULT_CANVAS_WIDTH
        self.canvas_height = DEFAULT_CANVAS_HEIGHT
        self.last_measurement_added = False

        self.angle_label = ft.Text(self.t("angle"), color=MUTED_COLOR, size=12)
        self.angle_text = ft.Text("0.00°", size=34, weight=ft.FontWeight.BOLD, color=RAZER_GREEN)
        self.quality_text = ft.Text(self.t("quality_none"), color=MUTED_COLOR)
        self.quality_bar = ft.ProgressBar(value=0, color=RAZER_GREEN, bgcolor=GRID_COLOR, height=8)
        self.status_text = ft.Text("", color=MUTED_COLOR, visible=False)
        self.canvas = cv.Canvas(
            expand=True,
            resize_interval=60,
            on_resize=self.on_canvas_resize,
            shapes=[],
        )

        self.start_button = ft.FilledButton(self.t("start"), icon=ft.Icons.PLAY_ARROW, on_click=self.start_recording)
        self.stop_button = ft.OutlinedButton(self.t("stop"), icon=ft.Icons.STOP, disabled=True, on_click=self.stop_recording)
        self.add_button = ft.OutlinedButton(self.t("add_to_series"), icon=ft.Icons.ADD, disabled=True, on_click=self.add_sample)
        self.header_add_button = ft.OutlinedButton(
            self.t("add_to_series"),
            icon=ft.Icons.ADD,
            disabled=True,
            on_click=self.add_sample,
        )
        self.remove_button = ft.OutlinedButton(self.t("remove_last"), icon=ft.Icons.UNDO, on_click=self.remove_last)
        self.clear_button = ft.OutlinedButton(self.t("clear_series"), icon=ft.Icons.DELETE_OUTLINE, on_click=self.clear_series)
        self.toggle_button = ft.TextButton(self.t("expand"), icon=ft.Icons.EXPAND_LESS, on_click=self.toggle_series)
        self.settings_button = ft.IconButton(icon=ft.Icons.SETTINGS, tooltip=self.t("settings"), on_click=self.open_settings)
        self.series_metrics = ft.Column(spacing=8, tight=True)
        self.recent_title = ft.Text(self.t("readings"), color=MUTED_COLOR, tooltip=self.t("readings_help"))
        self.recent_samples = ft.Text(self.t("empty_series"), color=MUTED_COLOR, selectable=True)
        self.series_body = ft.Row(spacing=24)
        self.series_header_metrics = ft.Row(spacing=14, expand=True)
        self.current_title = ft.Text(self.t("current_measurement"), size=18, weight=ft.FontWeight.BOLD)
        self.series_title = ft.Text(self.t("series"), size=16, weight=ft.FontWeight.BOLD)

    def t(self, key):
        return translate(self.language, key)

    def build(self):
        self.page.title = self.t("app_title")
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = BG_COLOR
        self.page.padding = 18
        self.page.window.width = 1120
        self.page.window.height = 760
        self.page.window.min_width = 900
        self.page.window.min_height = 620
        self.page.window.maximized = True
        self.page.on_keyboard_event = self.on_keyboard_event

        current_panel = ft.Container(
            expand=True,
            bgcolor=PANEL_COLOR,
            border_radius=8,
            padding=18,
            content=ft.Column(
                [
                    ft.GestureDetector(
                        expand=True,
                        mouse_cursor=ft.MouseCursor.CLICK,
                        on_tap_down=self.start_recording,
                        on_secondary_tap_down=self.stop_recording,
                        content=ft.Container(
                            expand=True,
                            bgcolor=PANEL_ALT_COLOR,
                            border=ft.Border.all(1, GRID_COLOR),
                            border_radius=8,
                            padding=8,
                            content=self.canvas,
                        ),
                    ),
                ],
                expand=True,
                spacing=14,
            ),
        )

        self.series_body.controls = [
            self.series_metrics,
            ft.VerticalDivider(width=1, color=GRID_COLOR),
            ft.Column(
                [
                    self.recent_title,
                    ft.Container(content=self.recent_samples, height=90),
                    ft.Row([self.add_button, self.remove_button, self.clear_button], wrap=True),
                ],
                expand=True,
                spacing=8,
            ),
        ]
        self.series_body.visible = not self.series_collapsed

        series_panel = ft.Container(
            bgcolor=PANEL_COLOR,
            border_radius=8,
            padding=14,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            self.series_title,
                            self.series_header_metrics,
                            ft.Row([self.header_add_button, self.toggle_button], spacing=8),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    self.series_body,
                ],
                spacing=10,
            ),
        )

        self.page.add(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Row(
                                [
                                    self.angle_label,
                                    self.angle_text,
                                    ft.Container(width=1, height=42, bgcolor=GRID_COLOR),
                                    ft.Column([self.quality_text, self.quality_bar], width=280, spacing=6),
                                ],
                                spacing=16,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Row([self.start_button, self.stop_button, self.settings_button], spacing=8),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    current_panel,
                    series_panel,
                ],
                expand=True,
                spacing=14,
            )
        )
        self.refresh_canvas([])
        self.refresh_series()
        self.recorder.start_listener()

    def set_status(self, message, color=MUTED_COLOR):
        self.status_text.value = message
        self.status_text.color = color
        self.page.schedule_update()

    def on_canvas_resize(self, event):
        self.canvas_width = max(event.width, 1)
        self.canvas_height = max(event.height, 1)
        if self.last_measurement:
            self.refresh_canvas(self.last_measurement.path, self.last_measurement.slope, self.last_measurement.intercept)
        else:
            self.refresh_canvas([])
        self.canvas.update()

    def start_recording(self, _=None):
        if self.recording:
            return

        self.recording = True
        self.last_measurement = None
        self.last_measurement_added = False
        self.add_button.disabled = True
        self.header_add_button.disabled = True
        self.start_button.disabled = True
        self.stop_button.disabled = False
        self.angle_text.value = "---"
        self.quality_text.value = self.t("quality_recording")
        self.quality_bar.value = 0
        self.refresh_canvas([])
        self.recorder.start_recording()
        self.set_status(self.t("stop_hint"), RAZER_GREEN)
        self.page.update()

    def stop_recording(self, _=None):
        if not self.recording:
            return

        self.recording = False
        measurement = self.recorder.stop_recording()
        self.last_measurement = measurement
        self.last_measurement_added = False
        self.start_button.disabled = False
        self.stop_button.disabled = True
        self.add_button.disabled = measurement.quality_score < 45
        self.header_add_button.disabled = measurement.quality_score < 45
        self.angle_text.value = f"{measurement.angle:.2f}°"
        self.quality_text.value = (
            f"{self.t('quality')}: {self.display_quality_label(measurement.quality_label)} · "
            f"{self.t('outliers')} {measurement.meta.rejected_delta_count} · "
            f"{self.t('noise')} {measurement.meta.rmse_ratio * 100:.1f}%"
        )
        self.quality_bar.value = measurement.quality_score / 100
        self.refresh_canvas(measurement.path, measurement.slope, measurement.intercept)
        self.set_status(self.t("add_hint"), MUTED_COLOR)
        self.page.update()

    def add_sample(self, _=None):
        if not self.last_measurement or self.last_measurement_added:
            return

        self.samples.append(self.last_measurement)
        self.last_measurement_added = True
        self.last_measurement = None
        self.add_button.disabled = True
        self.header_add_button.disabled = True
        self.refresh_series()
        self.set_status(self.t("status_added"), RAZER_GREEN)
        self.page.update()

    def remove_last(self, _=None):
        if self.samples:
            self.samples.pop()
            self.refresh_series()
            self.set_status(self.t("status_removed"), MUTED_COLOR)
            self.page.update()

    def clear_series(self, _=None):
        self.samples.clear()
        self.refresh_series()
        self.set_status(self.t("status_cleared"), MUTED_COLOR)
        self.page.update()

    def on_keyboard_event(self, event):
        if event.key == " " and self.last_measurement and not self.last_measurement_added:
            self.add_sample()

    def toggle_series(self, _=None):
        self.series_collapsed = not self.series_collapsed
        self.series_body.visible = not self.series_collapsed
        self.toggle_button.content = self.t("expand") if self.series_collapsed else self.t("collapse")
        self.toggle_button.icon = ft.Icons.EXPAND_LESS if self.series_collapsed else ft.Icons.EXPAND_MORE
        self.page.update()

    def toggle_filter(self, event):
        self.filter_enabled = bool(event.control.value)
        self.recorder.set_filter_enabled(self.filter_enabled)
        status = self.t("filter_on") if self.filter_enabled else self.t("filter_off")
        self.set_status(status, RAZER_GREEN if self.filter_enabled else MUTED_COLOR)

    def open_settings(self, _=None):
        filter_switch = ft.Switch(
            label=self.t("filter_outliers"),
            value=self.filter_enabled,
            active_color=RAZER_GREEN,
            on_change=self.toggle_filter,
            tooltip=self.t("filter_help"),
        )
        language_dropdown = ft.Dropdown(
            label=self.t("language"),
            value=self.language,
            width=220,
            options=[
                ft.dropdown.Option("en", "English"),
                ft.dropdown.Option("ru", "Русский"),
            ],
            on_select=self.change_language,
        )
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(self.t("settings")),
            content=ft.Column(
                [
                    filter_switch,
                    ft.Text(self.t("filter_help"), color=MUTED_COLOR),
                    ft.Divider(height=18, color=GRID_COLOR),
                    language_dropdown,
                ],
                tight=True,
                spacing=12,
            ),
            actions=[ft.TextButton(self.t("close"), on_click=lambda _: self.page.pop_dialog())],
        )
        self.page.show_dialog(dialog)

    def change_language(self, event):
        self.language = event.control.value or DEFAULT_LANGUAGE
        self.apply_language()
        self.page.update()

    def apply_language(self):
        self.page.title = self.t("app_title")
        self.angle_label.value = self.t("angle")
        self.start_button.content = self.t("start")
        self.stop_button.content = self.t("stop")
        self.add_button.content = self.t("add_to_series")
        self.header_add_button.content = self.t("add_to_series")
        self.remove_button.content = self.t("remove_last")
        self.clear_button.content = self.t("clear_series")
        self.toggle_button.content = self.t("expand") if self.series_collapsed else self.t("collapse")
        self.settings_button.tooltip = self.t("settings")
        self.current_title.value = self.t("current_measurement")
        self.series_title.value = self.t("series")
        self.recent_title.value = self.t("readings")
        self.recent_title.tooltip = self.t("readings_help")
        if self.recording:
            self.quality_text.value = self.t("quality_recording")
            self.status_text.value = self.t("stop_hint")
            self.status_text.color = RAZER_GREEN
        elif self.last_measurement:
            measurement = self.last_measurement
            self.quality_text.value = (
                f"{self.t('quality')}: {self.display_quality_label(measurement.quality_label)} · "
                f"{self.t('outliers')} {measurement.meta.rejected_delta_count} · "
                f"{self.t('noise')} {measurement.meta.rmse_ratio * 100:.1f}%"
            )
            self.status_text.value = self.t("add_hint")
            self.status_text.color = MUTED_COLOR
        else:
            self.quality_text.value = self.t("quality_none")
            self.status_text.value = self.t("start_hint")
            self.status_text.color = MUTED_COLOR
        self.refresh_series()
        if self.last_measurement:
            self.refresh_canvas(self.last_measurement.path, self.last_measurement.slope, self.last_measurement.intercept)
        else:
            self.refresh_canvas([])

    def display_quality_label(self, label):
        quality_keys = {
            "Коротко": "quality_short",
            "Отлично": "quality_excellent",
            "Хорошо": "quality_good",
            "Шумно": "quality_noisy",
            "Повторить": "quality_retry",
        }
        return self.t(quality_keys.get(label, label))

    def refresh_series(self):
        summary = summarize_series(self.samples)
        self.series_metrics.controls = [
            self.metric(self.t("samples"), summary.count, self.t("good_more_samples")),
            self.metric(self.t("mean"), self.format_angle(summary.mean), self.t("mean_help")),
            self.metric(self.t("median"), self.format_angle(summary.median), self.t("median_help")),
            self.metric(self.t("spread"), f"±{summary.spread:.2f}°", self.t("spread_help")),
            self.metric(self.t("stability"), f"{summary.stability}%", self.t("stability_help")),
        ]
        self.series_header_metrics.controls = [
            self.compact_metric(self.t("samples"), summary.count, self.t("good_more_samples")),
            self.compact_metric(self.t("mean"), self.format_angle(summary.mean), self.t("mean_help")),
            self.compact_metric(self.t("median"), self.format_angle(summary.median), self.t("median_help")),
            self.compact_metric(self.t("stability"), f"{summary.stability}%", self.t("stability_help")),
        ]
        self.recent_samples.value = "\n".join(
            f"#{index}  {sample.angle:.2f}°  {self.display_quality_label(sample.quality_label)}"
            for index, sample in list(enumerate(self.samples, start=1))[-5:][::-1]
        ) or self.t("empty_series")

    def metric(self, label, value, tooltip):
        return ft.Row(
            [
                ft.Text(label, color=MUTED_COLOR, width=110, tooltip=tooltip),
                ft.Text(str(value), color=RAZER_GREEN, weight=ft.FontWeight.BOLD, tooltip=tooltip),
            ],
            tight=True,
            spacing=8,
        )

    def compact_metric(self, label, value, tooltip):
        return ft.Row(
            [
                ft.Text(f"{label}:", color=MUTED_COLOR, size=12, tooltip=tooltip),
                ft.Text(str(value), color=RAZER_GREEN, size=12, weight=ft.FontWeight.BOLD, tooltip=tooltip),
            ],
            spacing=4,
            tight=True,
        )

    def refresh_canvas(self, path, slope=0.0, intercept=0.0):
        width = self.canvas_width
        height = self.canvas_height
        shapes = [
            cv.Rect(
                0,
                0,
                width,
                height,
                paint=ft.Paint(color=PANEL_ALT_COLOR, style=ft.PaintingStyle.FILL),
            ),
            cv.Line(0, height / 2, width, height / 2, paint=self.paint(GRID_COLOR, 1)),
            cv.Line(width / 2, 0, width / 2, height, paint=self.paint(GRID_COLOR, 1)),
        ]

        if len(path) >= 2:
            min_x = min(p[0] for p in path)
            max_x = max(p[0] for p in path)
            min_y = min(p[1] for p in path)
            max_y = max(p[1] for p in path)
            w_range = max(abs(max_x - min_x), 1)
            h_range = max(abs(max_y - min_y), 1)
            scale = min((width * 0.82) / w_range, (height * 0.78) / h_range)
            offset_x = (max_x + min_x) / 2
            offset_y = (max_y + min_y) / 2

            def screen(point):
                x, y = point
                return (
                    width / 2 + (x - offset_x) * scale,
                    height / 2 - (y - offset_y) * scale,
                )

            for i in range(1, len(path)):
                x1, y1 = screen(path[i - 1])
                x2, y2 = screen(path[i])
                shapes.append(cv.Line(x1, y1, x2, y2, paint=self.paint("#f4f4f4", 2)))

            if math.isinf(slope):
                p1 = screen((intercept, min_y))
                p2 = screen((intercept, max_y))
            else:
                p1 = screen((min_x, slope * min_x + intercept))
                p2 = screen((max_x, slope * max_x + intercept))
            shapes.append(cv.Line(p1[0], p1[1], p2[0], p2[1], paint=self.paint(RAZER_GREEN, 3)))
            if self.last_measurement and not self.last_measurement_added:
                shapes.append(
                    cv.Text(
                        24,
                        24,
                        self.t("add_hint"),
                        style=ft.TextStyle(size=14, color=RAZER_GREEN),
                    )
                )
        else:
            if self.recording:
                hint_key = "stop_hint"
            elif self.last_measurement and not self.last_measurement_added:
                hint_key = "add_hint"
            else:
                hint_key = "start_hint"
            shapes.append(
                cv.Text(
                    24,
                    24,
                    self.t(hint_key),
                    style=ft.TextStyle(size=14, color=MUTED_COLOR),
                )
            )

        self.canvas.shapes = shapes

    def paint(self, color, width):
        return ft.Paint(color=color, stroke_width=width, style=ft.PaintingStyle.STROKE)

    def format_angle(self, value):
        if not self.samples:
            return "—"
        return f"{value:.2f}°"


def main(page: ft.Page):
    MouseRotationApp(page).build()
