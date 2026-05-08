from dataclasses import dataclass, field


@dataclass
class MeasurementMeta:
    accepted_delta_count: int = 0
    rejected_delta_count: int = 0
    rejected_ratio: float = 0.0
    rmse_ratio: float = 0.0
    path_length: float = 0.0
    duration_seconds: float = 0.0


@dataclass
class SegmentMetrics:
    angle: float = 0.0
    rmse_ratio: float = 0.0
    length: float = 0.0
    avg_speed: float = 0.0
    peak_speed: float = 0.0


@dataclass
class SpeedProfile:
    avg_speed: float = 0.0
    peak_speed: float = 0.0
    speed_std: float = 0.0
    angle_low_speed: float = 0.0
    angle_mid_speed: float = 0.0
    angle_high_speed: float = 0.0


@dataclass
class MeasurementDiagnostics:
    confidence_score: int = 0
    confidence_label: str = "Low"
    linearity_score: int = 0
    curvature_score: int = 0
    local_angle_std: float = 0.0
    mean_curvature: float = 0.0
    max_curvature: float = 0.0
    start: SegmentMetrics = field(default_factory=SegmentMetrics)
    mid: SegmentMetrics = field(default_factory=SegmentMetrics)
    end: SegmentMetrics = field(default_factory=SegmentMetrics)
    speed: SpeedProfile = field(default_factory=SpeedProfile)


@dataclass
class Measurement:
    angle: float
    slope: float
    intercept: float
    path: list[tuple[float, float]]
    timestamps: list[float]
    meta: MeasurementMeta
    quality_score: int
    quality_label: str
    diagnostics: MeasurementDiagnostics = field(default_factory=MeasurementDiagnostics)


@dataclass
class SeriesSummary:
    count: int = 0
    mean: float = 0.0
    median: float = 0.0
    spread: float = 0.0
    stability: int = 0
    trimmed_mean: float = 0.0
    best_three_average: float = 0.0
    consistency_score: int = 0
