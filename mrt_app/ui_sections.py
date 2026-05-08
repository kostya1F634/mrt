import flet as ft

from mrt_app.theme import GRID_COLOR, MUTED_COLOR, PANEL_COLOR, RAZER_GREEN


class HeaderSection:
    def __init__(self, app):
        self.app = app
        self.angle_label = ft.Text(color=MUTED_COLOR, size=12)
        self.angle_value = ft.Text("0.00°", size=34, weight=ft.FontWeight.BOLD, color=RAZER_GREEN)
        self.quality_value = ft.Text(color=MUTED_COLOR)
        self.confidence_value = ft.Text(color=MUTED_COLOR)
        self.quality_bar = ft.ProgressBar(value=0, color=RAZER_GREEN, bgcolor=GRID_COLOR, height=8)
        self.confidence_bar = ft.ProgressBar(value=0, color=RAZER_GREEN, bgcolor=GRID_COLOR, height=8)
        self.settings_button = ft.IconButton(icon=ft.Icons.SETTINGS, on_click=self.app.open_settings)

    def build(self):
        return ft.Row(
            [
                ft.Row(
                    [
                        self.angle_label,
                        self.angle_value,
                        ft.Container(width=1, height=42, bgcolor=GRID_COLOR),
                        ft.Column([self.quality_value, self.quality_bar], width=360, spacing=6),
                        ft.Column([self.confidence_value, self.confidence_bar], width=220, spacing=6),
                    ],
                    spacing=16,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row([self.settings_button], spacing=8),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

    def apply_language(self):
        self.angle_label.value = self.app.t("angle")
        self.settings_button.tooltip = self.app.t("settings")

    def update(self, measurement=None, recording=False):
        self.apply_language()
        if recording:
            self.angle_value.value = "---"
            self.quality_value.value = self.app.t("quality_recording")
            self.confidence_value.value = self.app.t("confidence_none")
            self.quality_bar.value = 0
            self.confidence_bar.value = 0
            return

        if not measurement:
            self.angle_value.value = "0.00°"
            self.quality_value.value = self.app.t("quality_none")
            self.confidence_value.value = self.app.t("confidence_none")
            self.quality_bar.value = 0
            self.confidence_bar.value = 0
            return

        self.angle_value.value = f"{measurement.angle:.2f}°"
        self.quality_value.value = (
            f"{self.app.t('quality')}: {self.app.display_quality_label(measurement.quality_label)} · "
            f"{self.app.t('outliers')} {measurement.meta.rejected_delta_count} · "
            f"{self.app.t('noise')} {measurement.meta.rmse_ratio * 100:.1f}%"
        )
        self.confidence_value.value = (
            f"{self.app.t('confidence')}: "
            f"{self.app.display_confidence_label(measurement.diagnostics.confidence_label)} "
            f"({measurement.diagnostics.confidence_score}%)"
        )
        self.quality_bar.value = measurement.quality_score / 100
        self.confidence_bar.value = measurement.diagnostics.confidence_score / 100


class DiagnosticsSection:
    def __init__(self, app):
        self.app = app
        self.container = None
        self.linearity_metric = MetricBlock()
        self.curvature_metric = MetricBlock()
        self.start_card = SegmentCard()
        self.mid_card = SegmentCard()
        self.end_card = SegmentCard()
        self.avg_speed_metric = MetricBlock()
        self.peak_speed_metric = MetricBlock()
        self.speed_std_metric = MetricBlock()
        self.slow_speed_metric = MetricBlock()
        self.mid_speed_metric = MetricBlock()
        self.fast_speed_metric = MetricBlock()

    def build(self):
        self.container = ft.Container(
            width=820,
            bgcolor="#dd202020",
            border=ft.Border.all(1, GRID_COLOR),
            border_radius=8,
            padding=14,
            visible=False,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            self.linearity_metric.build(),
                            self.curvature_metric.build(),
                        ],
                        wrap=True,
                        spacing=16,
                    ),
                    ft.Text("", visible=False),  # keeps spacing predictable in older Flet layouts
                    ft.Text(self.app.t("segments"), color=MUTED_COLOR, tooltip=self.app.t("segment_help")),
                    ft.Row(
                        [
                            self.start_card.build(),
                            self.mid_card.build(),
                            self.end_card.build(),
                        ],
                        wrap=True,
                        spacing=12,
                    ),
                    ft.Text(self.app.t("speed_profile"), color=MUTED_COLOR, tooltip=self.app.t("speed_help")),
                    ft.Row(
                        [
                            self.avg_speed_metric.build(),
                            self.peak_speed_metric.build(),
                            self.speed_std_metric.build(),
                            self.slow_speed_metric.build(),
                            self.mid_speed_metric.build(),
                            self.fast_speed_metric.build(),
                        ],
                        wrap=True,
                        spacing=16,
                    ),
                ],
                spacing=10,
            ),
        )
        return self.container

    def apply_language(self):
        self.linearity_metric.update(self.app.t("linearity"), "—", self.app.t("linearity_help"))
        self.curvature_metric.update(self.app.t("curvature"), "—", self.app.t("curvature_help"))
        self.start_card.set_title(self.app.t("start"))
        self.mid_card.set_title(self.app.t("mid"))
        self.end_card.set_title(self.app.t("end"))
        self.avg_speed_metric.update(self.app.t("avg_speed"), "—", self.app.t("speed_help"))
        self.peak_speed_metric.update(self.app.t("peak_speed"), "—", self.app.t("speed_help"))
        self.speed_std_metric.update(self.app.t("speed_std"), "—", self.app.t("speed_help"))
        self.slow_speed_metric.update(self.app.t("slow"), "—", self.app.t("speed_help"))
        self.mid_speed_metric.update(self.app.t("medium"), "—", self.app.t("speed_help"))
        self.fast_speed_metric.update(self.app.t("fast"), "—", self.app.t("speed_help"))

    def update(self, measurement=None):
        self.apply_language()
        if not self.container:
            return
        self.container.visible = measurement is not None
        if not measurement:
            return

        diagnostics = measurement.diagnostics
        self.linearity_metric.update(
            self.app.t("linearity"),
            f"{diagnostics.linearity_score}%",
            self.app.t("linearity_help"),
        )
        self.curvature_metric.update(
            self.app.t("curvature"),
            f"{diagnostics.curvature_score}%",
            self.app.t("curvature_help"),
        )
        self.start_card.update(self.app, diagnostics.start)
        self.mid_card.update(self.app, diagnostics.mid)
        self.end_card.update(self.app, diagnostics.end)
        self.avg_speed_metric.update(self.app.t("avg_speed"), f"{diagnostics.speed.avg_speed:.1f}", self.app.t("speed_help"))
        self.peak_speed_metric.update(self.app.t("peak_speed"), f"{diagnostics.speed.peak_speed:.1f}", self.app.t("speed_help"))
        self.speed_std_metric.update(self.app.t("speed_std"), f"{diagnostics.speed.speed_std:.1f}", self.app.t("speed_help"))
        self.slow_speed_metric.update(self.app.t("slow"), self.app.format_angle(diagnostics.speed.angle_low_speed), self.app.t("speed_help"))
        self.mid_speed_metric.update(self.app.t("medium"), self.app.format_angle(diagnostics.speed.angle_mid_speed), self.app.t("speed_help"))
        self.fast_speed_metric.update(self.app.t("fast"), self.app.format_angle(diagnostics.speed.angle_high_speed), self.app.t("speed_help"))


class SeriesSection:
    def __init__(self, app):
        self.app = app
        self.series_metrics = ft.Column(spacing=8, tight=True)
        self.recent_title = ft.Text(color=MUTED_COLOR)
        self.recent_samples = ft.Text(color=MUTED_COLOR, selectable=True)
        self.body = ft.Row(spacing=24)
        self.header_metrics = ft.Row(spacing=14, expand=True)
        self.add_button = ft.OutlinedButton(icon=ft.Icons.ADD, disabled=True, on_click=self.app.add_sample)
        self.header_add_button = ft.OutlinedButton(icon=ft.Icons.ADD, disabled=True, on_click=self.app.add_sample)
        self.remove_button = ft.OutlinedButton(icon=ft.Icons.UNDO, on_click=self.app.remove_last)
        self.clear_button = ft.OutlinedButton(icon=ft.Icons.DELETE_OUTLINE, on_click=self.app.clear_series)
        self.toggle_button = ft.TextButton(icon=ft.Icons.EXPAND_LESS, on_click=self.app.toggle_series)
        self.title = ft.Text(size=16, weight=ft.FontWeight.BOLD)
        self.container = None

    def build(self):
        self.body.controls = [
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
        self.container = ft.Container(
            bgcolor=PANEL_COLOR,
            border_radius=8,
            padding=14,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            self.title,
                            self.header_metrics,
                            ft.Row([self.header_add_button, self.toggle_button], spacing=8),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    self.body,
                ],
                spacing=10,
            ),
        )
        return self.container

    def apply_language(self):
        self.title.value = self.app.t("series")
        self.recent_title.value = self.app.t("readings")
        self.recent_title.tooltip = self.app.t("readings_help")
        self.add_button.content = ft.Text(self.app.t("add_to_series"))
        self.header_add_button.content = ft.Text(self.app.t("add_to_series"))
        self.remove_button.content = ft.Text(self.app.t("remove_last"))
        self.clear_button.content = ft.Text(self.app.t("clear_series"))
        self.toggle_button.content = ft.Text(self.app.t("expand") if self.app.series_collapsed else self.app.t("collapse"))
        self.toggle_button.icon = ft.Icons.EXPAND_MORE if self.app.series_collapsed else ft.Icons.EXPAND_LESS

    def update(self, summary, samples, can_add):
        self.apply_language()
        self.body.visible = not self.app.series_collapsed
        self.header_metrics.visible = self.app.series_collapsed
        self.header_add_button.visible = self.app.series_collapsed
        self.add_button.disabled = not can_add
        self.header_add_button.disabled = not can_add
        self.series_metrics.controls = [
            metric_row(self.app.t("samples"), summary.count, self.app.t("good_more_samples")),
            metric_row(self.app.t("mean"), self.app.format_angle(summary.mean, allow_empty=samples), self.app.t("mean_help")),
            metric_row(self.app.t("median"), self.app.format_angle(summary.median, allow_empty=samples), self.app.t("median_help")),
            metric_row(self.app.t("spread"), f"±{summary.spread:.2f}°", self.app.t("spread_help")),
            metric_row(self.app.t("stability"), f"{summary.stability}%", self.app.t("stability_help")),
            metric_row(self.app.t("trimmed_mean"), self.app.format_angle(summary.trimmed_mean, allow_empty=samples), self.app.t("trimmed_mean_help")),
            metric_row(self.app.t("best_three_average"), self.app.format_angle(summary.best_three_average, allow_empty=samples), self.app.t("best_three_help")),
            metric_row(self.app.t("consistency"), f"{summary.consistency_score}%", self.app.t("consistency_help")),
        ]
        self.header_metrics.controls = [
            compact_metric(self.app.t("samples"), summary.count, self.app.t("good_more_samples")),
            compact_metric(self.app.t("mean"), self.app.format_angle(summary.mean, allow_empty=samples), self.app.t("mean_help")),
            compact_metric(self.app.t("median"), self.app.format_angle(summary.median, allow_empty=samples), self.app.t("median_help")),
            compact_metric(self.app.t("spread"), f"±{summary.spread:.2f}°", self.app.t("spread_help")),
            compact_metric(self.app.t("stability"), f"{summary.stability}%", self.app.t("stability_help")),
            compact_metric(self.app.t("consistency"), f"{summary.consistency_score}%", self.app.t("consistency_help")),
        ]
        self.recent_samples.value = "\n".join(
            f"#{index}  {sample.angle:.2f}°  {self.app.display_quality_label(sample.quality_label)}  "
            f"{self.app.display_confidence_label(sample.diagnostics.confidence_label)}"
            for index, sample in list(enumerate(samples, start=1))[-5:][::-1]
        ) or self.app.t("empty_series")


class MetricBlock:
    def __init__(self):
        self.label = ft.Text(color=MUTED_COLOR)
        self.value = ft.Text(color=RAZER_GREEN, weight=ft.FontWeight.BOLD, size=18)

    def build(self):
        return ft.Column([self.label, self.value], spacing=4)

    def update(self, label, value, tooltip):
        self.label.value = label
        self.label.tooltip = tooltip
        self.value.value = str(value)
        self.value.tooltip = tooltip


class SegmentCard:
    def __init__(self):
        self.title = ft.Text(weight=ft.FontWeight.BOLD)
        self.angle = ft.Text()
        self.noise = ft.Text()
        self.speed = ft.Text()

    def build(self):
        return ft.Container(
            width=220,
            padding=12,
            border=ft.Border.all(1, GRID_COLOR),
            border_radius=8,
            content=ft.Column([self.title, self.angle, self.noise, self.speed], spacing=6),
        )

    def set_title(self, title):
        self.title.value = title

    def update(self, app, metrics):
        self.angle.value = f"{app.t('segment_angle')}: {app.format_angle(metrics.angle)}"
        self.noise.value = f"{app.t('segment_noise')}: {metrics.rmse_ratio * 100:.1f}%"
        self.speed.value = f"{app.t('segment_speed')}: {metrics.avg_speed:.1f} / {metrics.peak_speed:.1f}"


def metric_row(label, value, tooltip):
    return ft.Row(
        [
            ft.Text(label, color=MUTED_COLOR, width=110, tooltip=tooltip),
            ft.Text(str(value), color=RAZER_GREEN, weight=ft.FontWeight.BOLD, tooltip=tooltip),
        ],
        tight=True,
        spacing=8,
    )


def compact_metric(label, value, tooltip):
    return ft.Row(
        [
            ft.Text(f"{label}:", color=MUTED_COLOR, size=12, tooltip=tooltip),
            ft.Text(str(value), color=RAZER_GREEN, size=12, weight=ft.FontWeight.BOLD, tooltip=tooltip),
        ],
        spacing=4,
        tight=True,
    )
