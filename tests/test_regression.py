import math
import unittest

from mrt_app.diagnostics import analyze_measurement, build_speed_profile, split_path_into_segments
from mrt_app.geometry import (
    apply_motion_delta,
    calculate_regression,
    orientation_mean_deg,
    orientation_std_deg,
    should_accept_motion_delta,
    summarize_series,
)
from mrt_app.models import Measurement, MeasurementDiagnostics, MeasurementMeta


def angle_for(path):
    angle, _, _ = calculate_regression(path)
    return angle


def build_measurement(angle, confidence, quality=90):
    return Measurement(
        angle=angle,
        slope=0.0,
        intercept=0.0,
        path=[],
        timestamps=[],
        meta=MeasurementMeta(),
        quality_score=quality,
        quality_label="Отлично",
        diagnostics=MeasurementDiagnostics(confidence_score=confidence, confidence_label="High"),
    )


class CalculateRegressionTests(unittest.TestCase):
    def assertAngleAlmostEqual(self, actual, expected, places=6):
        self.assertAlmostEqual(actual, expected, places=places)

    def test_empty_path_has_zero_angle(self):
        self.assertEqual(calculate_regression([]), (0.0, 0.0, 0.0))

    def test_stationary_path_has_zero_angle(self):
        self.assertEqual(calculate_regression([(3, 4), (3, 4)]), (0.0, 0.0, 4))

    def test_horizontal_line_has_zero_angle(self):
        self.assertAngleAlmostEqual(angle_for([(0, 0), (10, 0), (20, 0)]), 0.0)

    def test_positive_angle_for_upward_right_motion(self):
        self.assertAngleAlmostEqual(angle_for([(0, 0), (10, 10), (20, 20)]), 45.0)

    def test_negative_angle_for_downward_right_motion(self):
        self.assertAngleAlmostEqual(angle_for([(0, 0), (10, -10), (20, -20)]), -45.0)

    def test_vertical_line_returns_ninety_degrees_and_infinite_slope(self):
        angle, slope, intercept = calculate_regression([(5, 0), (5, 10), (5, 20)])

        self.assertAngleAlmostEqual(angle, 90.0)
        self.assertTrue(math.isinf(slope))
        self.assertEqual(intercept, 5)

    def test_noisy_horizontal_motion_stays_near_zero(self):
        path = [(-30, 1), (-20, -1), (-10, 1), (0, 0), (10, -1), (20, 1), (30, -1)]

        self.assertAlmostEqual(angle_for(path), 0.0, delta=1.0)

    def test_direction_is_preserved_for_reverse_motion(self):
        forward = [(0, 0), (10, 2), (20, 4), (30, 6)]
        backward = list(reversed(forward))

        self.assertAngleAlmostEqual(angle_for(backward), angle_for(forward))

    def test_stream_filter_rejects_vertical_motion_delta(self):
        self.assertFalse(should_accept_motion_delta([(0, 0), (10, 0)], 0, 20))

    def test_stream_filter_cuts_vertical_noise_between_horizontal_segments(self):
        path = [(0, 0)]
        deltas = [(10, 1), (10, -1), (0, 50), (10, 0), (10, 1)]

        accepted_count = 0
        for dx, dy in deltas:
            path, accepted = apply_motion_delta(path, dx, dy, filter_enabled=True)
            accepted_count += int(accepted)

        self.assertEqual(accepted_count, 4)
        self.assertEqual(path, [(0, 0), (10, 1), (20, 0), (30, 0), (40, 1)])
        self.assertAlmostEqual(angle_for(path), 0.0, delta=2.0)

    def test_stream_filter_rejects_large_arc_segment(self):
        path = [(0, 0)]
        for dx, dy in [(10, 0), (10, 1), (10, -1), (10, 0)]:
            path, _ = apply_motion_delta(path, dx, dy, filter_enabled=True)

        next_path, accepted = apply_motion_delta(path, 5, 20, filter_enabled=True)

        self.assertFalse(accepted)
        self.assertEqual(next_path, path)


class DiagnosticsTests(unittest.TestCase):
    def test_split_path_into_three_progress_segments(self):
        path = [(0, 0), (10, 0), (20, 1), (30, 2), (40, 2), (50, 3)]
        timestamps = [0, 1, 2, 3, 4, 5]

        start, mid, end = split_path_into_segments(path, timestamps)

        self.assertGreaterEqual(len(start[0]), 2)
        self.assertGreaterEqual(len(mid[0]), 2)
        self.assertGreaterEqual(len(end[0]), 2)
        self.assertEqual(start[0][0], (0, 0))
        self.assertEqual(end[0][-1], (50, 3))

    def test_analyze_measurement_reports_high_confidence_for_clean_swipe(self):
        path = [(0, 0), (20, 0), (40, 1), (60, 1), (80, 2), (100, 2), (120, 3)]
        timestamps = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
        meta = MeasurementMeta(
            accepted_delta_count=6,
            rejected_delta_count=0,
            rejected_ratio=0.0,
            rmse_ratio=0.01,
            path_length=120.0,
            duration_seconds=0.6,
        )

        diagnostics = analyze_measurement(path, timestamps, meta)

        self.assertGreaterEqual(diagnostics.confidence_score, 70)
        self.assertGreaterEqual(diagnostics.linearity_score, 70)
        self.assertGreaterEqual(diagnostics.curvature_score, 60)
        self.assertGreater(diagnostics.speed.peak_speed, 0.0)

    def test_analyze_measurement_detects_end_drift(self):
        path = [(0, 0), (20, 0), (40, 0), (60, 2), (80, 7), (100, 14)]
        timestamps = [0, 0.1, 0.2, 0.3, 0.4, 0.5]
        meta = MeasurementMeta(
            accepted_delta_count=5,
            rejected_delta_count=1,
            rejected_ratio=1 / 6,
            rmse_ratio=0.04,
            path_length=102.0,
            duration_seconds=0.5,
        )

        diagnostics = analyze_measurement(path, timestamps, meta)

        self.assertGreater(diagnostics.end.angle, diagnostics.start.angle)
        self.assertGreaterEqual(diagnostics.speed.angle_high_speed, diagnostics.speed.angle_low_speed)

    def test_orientation_stats_wrap_cleanly_near_ninety_degrees(self):
        angles = [89.0, -89.0]

        self.assertAlmostEqual(abs(orientation_mean_deg(angles)), 90.0, delta=1.0)
        self.assertLess(orientation_std_deg(angles), 5.0)

    def test_curvature_is_similar_for_same_line_with_different_sampling_density(self):
        sparse_path = [(0, 0), (30, 1), (60, 2), (90, 3)]
        dense_path = [(0, 0), (15, 0.5), (30, 1), (45, 1.5), (60, 2), (75, 2.5), (90, 3)]
        sparse_times = [0.0, 0.1, 0.2, 0.3]
        dense_times = [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3]
        sparse_meta = MeasurementMeta(path_length=90.0, rmse_ratio=0.01)
        dense_meta = MeasurementMeta(path_length=90.0, rmse_ratio=0.01)

        sparse = analyze_measurement(sparse_path, sparse_times, sparse_meta)
        dense = analyze_measurement(dense_path, dense_times, dense_meta)

        self.assertAlmostEqual(sparse.mean_curvature, dense.mean_curvature, delta=0.2)
        self.assertAlmostEqual(sparse.linearity_score, dense.linearity_score, delta=10)

    def test_speed_profile_bins_do_not_duplicate_steps(self):
        path = [(0, 0), (10, 0), (30, 0)]
        timestamps = [0.0, 0.1, 0.2]

        profile = build_speed_profile(path, timestamps)

        self.assertGreater(profile.angle_low_speed, -1.0)
        self.assertGreater(profile.angle_mid_speed, -1.0)
        self.assertEqual(profile.angle_high_speed, 0.0)


class SeriesSummaryTests(unittest.TestCase):
    def test_summarize_series_returns_extended_consistency_metrics(self):
        summary = summarize_series(
            [
                build_measurement(1.0, 90),
                build_measurement(2.0, 80),
                build_measurement(3.0, 70),
                build_measurement(4.0, 95),
                build_measurement(5.0, 60),
            ]
        )

        self.assertEqual(summary.count, 5)
        self.assertEqual(summary.mean, 3.0)
        self.assertEqual(summary.median, 3.0)
        self.assertAlmostEqual(summary.trimmed_mean, 3.0)
        self.assertAlmostEqual(summary.best_three_average, (4.0 + 1.0 + 2.0) / 3, places=3)
        self.assertGreater(summary.consistency_score, 0)

    def test_summarize_empty_series(self):
        summary = summarize_series([])

        self.assertEqual(summary.count, 0)
        self.assertEqual(summary.mean, 0.0)
        self.assertEqual(summary.median, 0.0)
        self.assertEqual(summary.trimmed_mean, 0.0)

    def test_series_summary_uses_circular_angle_statistics(self):
        summary = summarize_series(
            [
                build_measurement(89.0, 80),
                build_measurement(-89.0, 85),
            ]
        )

        self.assertAlmostEqual(abs(summary.mean), 90.0, delta=1.0)
        self.assertLess(summary.spread, 5.0)


if __name__ == "__main__":
    unittest.main()
