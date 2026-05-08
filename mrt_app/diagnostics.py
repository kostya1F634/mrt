import math
import statistics

from mrt_app.geometry import (
    calculate_path_length,
    calculate_path_quality,
    calculate_regression,
    normalize_motion_angle,
    orientation_distance_deg,
    orientation_mean_deg,
    orientation_std_deg,
)
from mrt_app.models import MeasurementDiagnostics, MeasurementMeta, SegmentMetrics, SpeedProfile


TARGET_CONFIDENCE_LENGTH = 160.0
MAX_CONFIDENCE_RMSE_RATIO = 0.10
MAX_CONFIDENCE_REJECTED_RATIO = 0.35
MAX_LOCAL_ANGLE_STD = 12.0
MAX_SEGMENT_ANGLE_STD = 8.0
MAX_MEAN_CURVATURE = 8.0


def analyze_measurement(path, timestamps, meta: MeasurementMeta):
    start, mid, end = split_path_into_segments(path, timestamps)
    start_metrics = build_segment_metrics(*start)
    mid_metrics = build_segment_metrics(*mid)
    end_metrics = build_segment_metrics(*end)
    local_angles, step_lengths = calculate_local_angles(path)
    local_angle_std = orientation_std_deg(local_angles, weights=step_lengths)
    curvature_values = calculate_curvature_values(local_angles, step_lengths)
    mean_curvature = statistics.fmean(curvature_values) if curvature_values else 0.0
    max_curvature = max(curvature_values, default=0.0)
    linearity_score = score_inverse(local_angle_std, MAX_LOCAL_ANGLE_STD)
    curvature_score = score_inverse(mean_curvature, MAX_MEAN_CURVATURE)
    speed_profile = build_speed_profile(path, timestamps)
    confidence_score = calculate_confidence_score(
        meta=meta,
        local_angle_std=local_angle_std,
        segment_angles=[start_metrics.angle, mid_metrics.angle, end_metrics.angle],
    )

    return MeasurementDiagnostics(
        confidence_score=confidence_score,
        confidence_label=confidence_label(confidence_score),
        linearity_score=linearity_score,
        curvature_score=curvature_score,
        local_angle_std=local_angle_std,
        mean_curvature=mean_curvature,
        max_curvature=max_curvature,
        start=start_metrics,
        mid=mid_metrics,
        end=end_metrics,
        speed=speed_profile,
    )


def build_segment_metrics(path, timestamps):
    if len(path) < 2:
        return SegmentMetrics()

    quality = calculate_path_quality(path)
    angle, _, _ = calculate_regression(path)
    speeds = calculate_step_speeds(path, timestamps)
    return SegmentMetrics(
        angle=angle,
        rmse_ratio=quality["rmse_ratio"],
        length=calculate_path_length(path),
        avg_speed=statistics.fmean(speeds) if speeds else 0.0,
        peak_speed=max(speeds, default=0.0),
    )


def split_path_into_segments(path, timestamps):
    if len(path) < 2:
        empty_path = list(path)
        empty_timestamps = list(timestamps)
        return (empty_path, empty_timestamps), (empty_path, empty_timestamps), (empty_path, empty_timestamps)

    cumulative = [0.0]
    for index in range(1, len(path)):
        cumulative.append(cumulative[-1] + math.hypot(path[index][0] - path[index - 1][0], path[index][1] - path[index - 1][1]))

    total_length = cumulative[-1]
    if total_length <= 0:
        duplicate = (list(path), list(timestamps))
        return duplicate, duplicate, duplicate

    first_cut = total_length / 3
    second_cut = 2 * total_length / 3
    first_index = next((idx for idx, value in enumerate(cumulative) if value >= first_cut), len(path) - 1)
    second_index = next((idx for idx, value in enumerate(cumulative) if value >= second_cut), len(path) - 1)
    first_index = max(1, min(first_index, len(path) - 2))
    second_index = max(first_index + 1, min(second_index, len(path) - 1))

    start = (path[: first_index + 1], timestamps[: first_index + 1])
    mid = (path[first_index: second_index + 1], timestamps[first_index: second_index + 1])
    end = (path[second_index:], timestamps[second_index:])
    return start, mid, end


def calculate_local_angles(path):
    local_angles = []
    step_lengths = []
    for index in range(1, len(path)):
        dx = path[index][0] - path[index - 1][0]
        dy = path[index][1] - path[index - 1][1]
        step_length = math.hypot(dx, dy)
        if step_length == 0:
            continue
        local_angles.append(normalize_motion_angle(dx, dy))
        step_lengths.append(step_length)
    return local_angles, step_lengths


def calculate_curvature_values(local_angles, step_lengths):
    curvature_values = []
    for index in range(1, len(local_angles)):
        delta_angle = orientation_distance_deg(local_angles[index], local_angles[index - 1])
        effective_step = max((step_lengths[index] + step_lengths[index - 1]) / 2.0, 1e-9)
        curvature_values.append(delta_angle / effective_step)
    return curvature_values


def calculate_step_speeds(path, timestamps):
    speeds = []
    for index in range(1, len(path)):
        dt = timestamps[index] - timestamps[index - 1]
        if dt <= 0:
            continue
        distance = math.hypot(path[index][0] - path[index - 1][0], path[index][1] - path[index - 1][1])
        speeds.append(distance / dt)
    return speeds


def build_speed_profile(path, timestamps):
    step_data = []
    for index in range(1, len(path)):
        dt = timestamps[index] - timestamps[index - 1]
        if dt <= 0:
            continue
        dx = path[index][0] - path[index - 1][0]
        dy = path[index][1] - path[index - 1][1]
        distance = math.hypot(dx, dy)
        if distance <= 0:
            continue
        step_data.append((distance / dt, normalize_motion_angle(dx, dy)))

    if not step_data:
        return SpeedProfile()

    step_speeds = [item[0] for item in step_data]
    sorted_steps = sorted(step_data, key=lambda item: item[0])
    low_group, mid_group, high_group = split_evenly(sorted_steps, 3)
    return SpeedProfile(
        avg_speed=statistics.fmean(step_speeds),
        peak_speed=max(step_speeds),
        speed_std=statistics.pstdev(step_speeds) if len(step_speeds) > 1 else 0.0,
        angle_low_speed=average_angles(low_group),
        angle_mid_speed=average_angles(mid_group),
        angle_high_speed=average_angles(high_group),
    )


def split_evenly(items, groups):
    result = []
    count = len(items)
    for group_index in range(groups):
        start = math.floor(group_index * count / groups)
        end = math.floor((group_index + 1) * count / groups)
        result.append(items[start:end])
    return result


def average_angles(speed_group):
    if not speed_group:
        return 0.0
    return orientation_mean_deg([angle for _, angle in speed_group])


def calculate_confidence_score(meta, local_angle_std, segment_angles):
    path_length_score = clamp(meta.path_length / TARGET_CONFIDENCE_LENGTH, 0.0, 1.0)
    rmse_score = 1.0 - clamp(meta.rmse_ratio / MAX_CONFIDENCE_RMSE_RATIO, 0.0, 1.0)
    rejection_score = 1.0 - clamp(meta.rejected_ratio / MAX_CONFIDENCE_REJECTED_RATIO, 0.0, 1.0)
    angle_stability_score = 1.0 - clamp(local_angle_std / MAX_LOCAL_ANGLE_STD, 0.0, 1.0)
    segment_std = orientation_std_deg(segment_angles) if len(segment_angles) > 1 else 0.0
    segment_consistency_score = 1.0 - clamp(segment_std / MAX_SEGMENT_ANGLE_STD, 0.0, 1.0)
    score = round(
        100
        * (
            0.25 * path_length_score
            + 0.25 * rmse_score
            + 0.20 * rejection_score
            + 0.20 * angle_stability_score
            + 0.10 * segment_consistency_score
        )
    )
    return max(0, min(100, score))


def confidence_label(score):
    if score >= 70:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


def score_inverse(value, threshold):
    if threshold <= 0:
        return 0
    return max(0, min(100, round(100 * (1.0 - clamp(value / threshold, 0.0, 1.0)))))


def clamp(value, lower, upper):
    return max(lower, min(upper, value))
