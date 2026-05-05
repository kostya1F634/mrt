import math
import statistics

from mrt_app.models import MeasurementMeta, SeriesSummary


MIN_FILTER_SPAN_X = 20.0
MAX_FILTER_ABS_ANGLE = 35.0
MAX_FILTER_RMSE_RATIO = 0.08
FILTER_WINDOW_POINTS = 16


def calculate_regression(path):
    if len(path) < 2:
        return 0.0, 0.0, 0.0

    mean_x = sum(p[0] for p in path) / len(path)
    mean_y = sum(p[1] for p in path) / len(path)

    sxx = sum((p[0] - mean_x) ** 2 for p in path)
    syy = sum((p[1] - mean_y) ** 2 for p in path)
    sxy = sum((p[0] - mean_x) * (p[1] - mean_y) for p in path)

    if sxx == 0 and syy == 0:
        return 0.0, 0.0, mean_y

    angle_degrees = 0.5 * math.degrees(math.atan2(2 * sxy, sxx - syy))
    if angle_degrees > 90:
        angle_degrees -= 180
    elif angle_degrees < -90:
        angle_degrees += 180

    angle_radians = math.radians(angle_degrees)
    if abs(math.cos(angle_radians)) < 1e-12:
        return angle_degrees, float("inf"), mean_x

    slope = math.tan(angle_radians)
    intercept = mean_y - slope * mean_x
    return angle_degrees, slope, intercept


def calculate_path_quality(path):
    if len(path) < 2:
        return {
            "accepted": False,
            "reason": "Слишком мало точек для расчета.",
            "angle": 0.0,
            "m": 0.0,
            "b": 0.0,
            "rmse_ratio": 1.0,
        }

    angle, slope, intercept = calculate_regression(path)
    min_x = min(p[0] for p in path)
    max_x = max(p[0] for p in path)
    min_y = min(p[1] for p in path)
    max_y = max(p[1] for p in path)
    span_x = max_x - min_x
    span_y = max_y - min_y
    span = max(math.hypot(span_x, span_y), 1.0)

    if math.isinf(slope):
        residuals = [abs(p[0] - intercept) for p in path]
    else:
        residual_scale = math.sqrt(slope * slope + 1)
        residuals = [abs(slope * p[0] - p[1] + intercept) / residual_scale for p in path]

    rmse = math.sqrt(sum(r * r for r in residuals) / len(residuals))
    rmse_ratio = rmse / span

    accepted = True
    reason = "Траектория принята."
    if span_x < MIN_FILTER_SPAN_X:
        accepted = False
        reason = "Недостаточно горизонтального движения."
    elif abs(angle) > MAX_FILTER_ABS_ANGLE:
        accepted = False
        reason = "Траектория слишком вертикальная."
    elif rmse_ratio > MAX_FILTER_RMSE_RATIO:
        accepted = False
        reason = "Траектория слишком дугообразная или неровная."

    return {
        "accepted": accepted,
        "reason": reason,
        "angle": angle,
        "m": slope,
        "b": intercept,
        "rmse_ratio": rmse_ratio,
    }


def normalize_motion_angle(dx, dy):
    angle = math.degrees(math.atan2(dy, dx))
    if angle > 90:
        angle -= 180
    elif angle <= -90:
        angle += 180
    return angle


def should_accept_motion_delta(path, dx, dy):
    if dx == 0 and dy == 0:
        return False

    if abs(normalize_motion_angle(dx, dy)) > MAX_FILTER_ABS_ANGLE:
        return False

    if len(path) < 3:
        return True

    last_x, last_y = path[-1]
    candidate = (last_x + dx, last_y + dy)
    window = (path + [candidate])[-FILTER_WINDOW_POINTS:]
    quality = calculate_path_quality(window)
    return quality["accepted"] or quality["reason"] == "Недостаточно горизонтального движения."


def apply_motion_delta(path, dx, dy, filter_enabled):
    if not path:
        path = [(0, 0)]

    if dx == 0 and dy == 0:
        return path, False

    if filter_enabled and not should_accept_motion_delta(path, dx, dy):
        return path, False

    last_x, last_y = path[-1]
    return path + [(last_x + dx, last_y + dy)], True


def calculate_path_length(path):
    return sum(
        math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1])
        for i in range(1, len(path))
    )


def quality_score_from_meta(meta: MeasurementMeta, path):
    length = calculate_path_length(path)
    if length < 50:
        return 25, "Коротко"

    rmse_penalty = min(meta.rmse_ratio / MAX_FILTER_RMSE_RATIO, 2.0) * 35
    rejected_penalty = min(meta.rejected_ratio, 0.5) * 80
    score = max(0, min(100, round(100 - rmse_penalty - rejected_penalty)))

    if score >= 85:
        label = "Отлично"
    elif score >= 65:
        label = "Хорошо"
    elif score >= 45:
        label = "Шумно"
    else:
        label = "Повторить"

    return score, label


def summarize_series(samples):
    if not samples:
        return SeriesSummary()

    angles = [sample.angle for sample in samples]
    spread = statistics.pstdev(angles) if len(angles) > 1 else 0.0
    stability = max(0, min(100, round(100 - spread * 20)))
    return SeriesSummary(
        count=len(samples),
        mean=statistics.fmean(angles),
        median=statistics.median(angles),
        spread=spread,
        stability=stability,
    )
