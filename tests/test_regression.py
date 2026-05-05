import math
import unittest

from main import apply_motion_delta, calculate_regression, should_accept_motion_delta, summarize_series


def angle_for(path):
    angle, _, _ = calculate_regression(path)
    return angle


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

    def test_summarize_series_returns_mean_median_and_stability(self):
        summary = summarize_series([
            {"angle": 1.0},
            {"angle": 2.0},
            {"angle": 3.0},
        ])

        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["mean"], 2.0)
        self.assertEqual(summary["median"], 2.0)
        self.assertGreater(summary["stability"], 0)

    def test_summarize_empty_series(self):
        summary = summarize_series([])

        self.assertEqual(summary["count"], 0)
        self.assertEqual(summary["mean"], 0.0)
        self.assertEqual(summary["median"], 0.0)


if __name__ == "__main__":
    unittest.main()
