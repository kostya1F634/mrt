import asyncio
import math
from pathlib import Path

import flet as ft
import flet.canvas as cv

from mrt_app.geometry import summarize_series
from mrt_app.i18n import DEFAULT_LANGUAGE, translate
from mrt_app.input_listener import MouseInputRecorder
from mrt_app.theme import BG_COLOR, GRID_COLOR, MUTED_COLOR, PANEL_ALT_COLOR, PANEL_COLOR, RAZER_GREEN
from mrt_app.ui_sections import DiagnosticsSection, HeaderSection, SeriesSection


DEFAULT_CANVAS_WIDTH = 900
DEFAULT_CANVAS_HEIGHT = 320


class MouseRotationApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.recorder = MouseInputRecorder(on_status=self.set_status)
        self.samples = []
        self.last_measurement = None
        self.last_measurement_added = False
        self.series_collapsed = True
        self.recording = False
        self.filter_enabled = False
        self.language = DEFAULT_LANGUAGE
        self.canvas_width = DEFAULT_CANVAS_WIDTH
        self.canvas_height = DEFAULT_CANVAS_HEIGHT
        self.show_diagnostics = True
        self.show_series = True
        self.status_text = ft.Text("", color=MUTED_COLOR, visible=False)
        self.canvas = cv.Canvas(expand=True, resize_interval=60, on_resize=self.on_canvas_resize, shapes=[])
        self.header_section = HeaderSection(self)
        self.diagnostics_section = DiagnosticsSection(self)
        self.series_section = SeriesSection(self)
        self.section_controls = {}

    def t(self, key):
        return translate(self.language, key)

    def build(self):
        self.page.title = self.t("app_title")
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = BG_COLOR
        self.page.padding = 18
        icon_path = Path("assets/icon.png")
        if icon_path.exists():
            self.page.window.icon = str(icon_path.resolve())
        self.page.window.width = 1120
        self.page.window.height = 760
        self.page.window.min_width = 900
        self.page.window.min_height = 620
        self.page.window.maximized = True
        self.page.on_keyboard_event = self.on_keyboard_event
        self.page.on_resize = self.on_page_resize

        diagnostics_overlay = ft.Container(
            expand=True,
            padding=12,
            content=ft.Column(
                [
                    ft.Container(expand=True),
                    ft.Row([self.diagnostics_section.build()], alignment=ft.MainAxisAlignment.START),
                ],
                expand=True,
                spacing=0,
            ),
        )

        current_panel = ft.Container(
            expand=True,
            bgcolor=PANEL_COLOR,
            border_radius=8,
            padding=18,
            content=ft.GestureDetector(
                expand=True,
                mouse_cursor=ft.MouseCursor.CLICK,
                on_tap_down=self.start_recording,
                on_secondary_tap_down=self.stop_recording,
                content=ft.Stack(
                    [
                        ft.Container(
                            expand=True,
                            bgcolor=PANEL_ALT_COLOR,
                            border=ft.Border.all(1, GRID_COLOR),
                            border_radius=8,
                            padding=8,
                            content=self.canvas,
                        ),
                        diagnostics_overlay,
                    ],
                    expand=True,
                ),
            ),
        )

        self.section_controls = {
            "header": self.header_section.build(),
            "current": current_panel,
            "diagnostics": diagnostics_overlay,
            "series": self.series_section.build(),
        }
        self.section_controls["diagnostics"].visible = True
        self.section_controls["series"].visible = self.show_series

        self.page.add(
            ft.Column(
                [
                    self.section_controls["header"],
                    self.section_controls["current"],
                    self.section_controls["series"],
                ],
                expand=True,
                spacing=14,
            )
        )
        self.apply_language()
        self.refresh_canvas([])
        self.refresh_series()
        self.refresh_diagnostics()
        self.recorder.start_listener()
        self.page.run_task(self.post_mount_refresh)

    def set_status(self, message, color=MUTED_COLOR):
        self.status_text.value = message
        self.status_text.color = color
        if self.status_text.visible:
            self.page.schedule_update()

    def on_canvas_resize(self, event):
        self.canvas_width = max(event.width, 1)
        self.canvas_height = max(event.height, 1)
        self.refresh_current_canvas()
        self.canvas.update()

    def on_page_resize(self, _event):
        self.page.run_task(self.post_mount_refresh)

    async def post_mount_refresh(self):
        for delay in (0.0, 0.05, 0.15):
            if delay:
                await asyncio.sleep(delay)
            self.refresh_current_canvas()
            self.page.update()

    def refresh_current_canvas(self):
        if self.last_measurement:
            self.refresh_canvas(self.last_measurement.path, self.last_measurement.slope, self.last_measurement.intercept)
        else:
            self.refresh_canvas([])

    def start_recording(self, _=None):
        if self.recording:
            return

        self.recording = True
        self.last_measurement = None
        self.last_measurement_added = False
        self.recorder.start_recording()
        self.header_section.update(recording=True)
        self.refresh_diagnostics()
        self.refresh_series()
        self.refresh_canvas([])
        self.set_status(self.t("stop_hint"), RAZER_GREEN)

    def stop_recording(self, _=None):
        if not self.recording:
            return

        self.recording = False
        self.last_measurement = self.recorder.stop_recording()
        self.last_measurement_added = False
        self.header_section.update(self.last_measurement, recording=False)
        self.refresh_diagnostics()
        self.refresh_series()
        self.refresh_canvas(self.last_measurement.path, self.last_measurement.slope, self.last_measurement.intercept)
        self.set_status(self.t("add_hint"), MUTED_COLOR)

    def add_sample(self, _=None):
        if not self.last_measurement or self.last_measurement_added:
            return

        self.samples.append(self.last_measurement)
        self.last_measurement_added = True
        self.last_measurement = None
        self.refresh_series()
        self.refresh_diagnostics()
        self.header_section.update(None, recording=False)
        self.refresh_canvas([])
        self.set_status(self.t("status_added"), RAZER_GREEN)

    def remove_last(self, _=None):
        if self.samples:
            self.samples.pop()
            self.refresh_series()
            self.set_status(self.t("status_removed"), MUTED_COLOR)

    def clear_series(self, _=None):
        self.samples.clear()
        self.refresh_series()
        self.set_status(self.t("status_cleared"), MUTED_COLOR)

    def on_keyboard_event(self, event):
        if event.key == " " and self.last_measurement and not self.last_measurement_added:
            self.add_sample()

    def toggle_series(self, _=None):
        self.series_collapsed = not self.series_collapsed
        self.refresh_series()

    def toggle_filter(self, event):
        self.filter_enabled = bool(event.control.value)
        self.recorder.set_filter_enabled(self.filter_enabled)
        status = self.t("filter_on") if self.filter_enabled else self.t("filter_off")
        self.set_status(status, RAZER_GREEN if self.filter_enabled else MUTED_COLOR)

    def toggle_diagnostics_visibility(self, event):
        self.show_diagnostics = bool(event.control.value)
        self.refresh_diagnostics()

    def toggle_series_visibility(self, event):
        self.show_series = bool(event.control.value)
        self.section_controls["series"].visible = self.show_series

    def open_settings(self, _=None):
        filter_switch = ft.Switch(
            label=self.t("filter_outliers"),
            value=self.filter_enabled,
            active_color=RAZER_GREEN,
            on_change=self.toggle_filter,
            tooltip=self.t("filter_help"),
        )
        diagnostics_switch = ft.Switch(
            label=self.t("additional_info"),
            value=self.show_diagnostics,
            active_color=RAZER_GREEN,
            on_change=self.toggle_diagnostics_visibility,
        )
        series_switch = ft.Switch(
            label=self.t("series"),
            value=self.show_series,
            active_color=RAZER_GREEN,
            on_change=self.toggle_series_visibility,
        )
        language_dropdown = ft.Dropdown(
            label=self.t("language"),
            value=self.language,
            width=220,
            options=[ft.dropdown.Option("en", "English"), ft.dropdown.Option("ru", "Русский")],
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
                    diagnostics_switch,
                    series_switch,
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

    def apply_language(self):
        self.page.title = self.t("app_title")
        self.header_section.update(self.last_measurement, recording=self.recording)
        self.diagnostics_section.update(self.last_measurement if self.show_diagnostics else None)
        self.refresh_series()
        self.refresh_current_canvas()

    def display_quality_label(self, label):
        quality_keys = {
            "Коротко": "quality_short",
            "Отлично": "quality_excellent",
            "Хорошо": "quality_good",
            "Шумно": "quality_noisy",
            "Повторить": "quality_retry",
        }
        return self.t(quality_keys.get(label, label))

    def display_confidence_label(self, label):
        return self.t(
            {
                "High": "confidence_high",
                "Medium": "confidence_medium",
                "Low": "confidence_low",
            }.get(label, "confidence_low")
        )

    def refresh_series(self):
        summary = summarize_series(self.samples)
        can_add = bool(self.last_measurement and not self.last_measurement_added and self.last_measurement.quality_score >= 45)
        self.section_controls["series"].visible = self.show_series
        self.series_section.update(summary, self.samples, can_add)

    def refresh_diagnostics(self):
        measurement = self.last_measurement if self.show_diagnostics else None
        self.diagnostics_section.container.visible = self.show_diagnostics and measurement is not None
        self.diagnostics_section.update(measurement)

    def refresh_canvas(self, path, slope=0.0, intercept=0.0):
        width = self.canvas_width
        height = self.canvas_height
        shapes = [
            cv.Rect(0, 0, width, height, paint=ft.Paint(color=PANEL_ALT_COLOR, style=ft.PaintingStyle.FILL)),
            cv.Line(0, height / 2, width, height / 2, paint=self.paint(GRID_COLOR, 1)),
            cv.Line(width / 2, 0, width / 2, height, paint=self.paint(GRID_COLOR, 1)),
        ]

        if len(path) >= 2:
            min_x = min(point[0] for point in path)
            max_x = max(point[0] for point in path)
            min_y = min(point[1] for point in path)
            max_y = max(point[1] for point in path)
            w_range = max(abs(max_x - min_x), 1)
            h_range = max(abs(max_y - min_y), 1)
            scale = min((width * 0.82) / w_range, (height * 0.78) / h_range)
            offset_x = (max_x + min_x) / 2
            offset_y = (max_y + min_y) / 2

            def screen(point):
                x, y = point
                return (width / 2 + (x - offset_x) * scale, height / 2 - (y - offset_y) * scale)

            for index in range(1, len(path)):
                x1, y1 = screen(path[index - 1])
                x2, y2 = screen(path[index])
                shapes.append(cv.Line(x1, y1, x2, y2, paint=self.paint("#f4f4f4", 2)))

            if math.isinf(slope):
                p1 = screen((intercept, min_y))
                p2 = screen((intercept, max_y))
            else:
                p1 = screen((min_x, slope * min_x + intercept))
                p2 = screen((max_x, slope * max_x + intercept))
            shapes.append(cv.Line(p1[0], p1[1], p2[0], p2[1], paint=self.paint(RAZER_GREEN, 3)))
            if self.last_measurement and not self.last_measurement_added:
                shapes.append(cv.Text(24, 24, self.t("add_hint"), style=ft.TextStyle(size=14, color=RAZER_GREEN)))
        else:
            if self.recording:
                hint_key = "stop_hint"
            elif self.last_measurement and not self.last_measurement_added:
                hint_key = "add_hint"
            else:
                hint_key = "start_hint"
            shapes.append(cv.Text(24, 24, self.t(hint_key), style=ft.TextStyle(size=14, color=MUTED_COLOR)))

        self.canvas.shapes = shapes

    def paint(self, color, width):
        return ft.Paint(color=color, stroke_width=width, style=ft.PaintingStyle.STROKE)

    def format_angle(self, value, allow_empty=None):
        if allow_empty is not None and not allow_empty:
            return "—"
        return f"{value:.2f}°"


def main(page: ft.Page):
    MouseRotationApp(page).build()
