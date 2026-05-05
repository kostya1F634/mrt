from dataclasses import dataclass


@dataclass
class MeasurementMeta:
    accepted_delta_count: int = 0
    rejected_delta_count: int = 0
    rejected_ratio: float = 0.0
    rmse_ratio: float = 0.0


@dataclass
class Measurement:
    angle: float
    slope: float
    intercept: float
    path: list[tuple[float, float]]
    meta: MeasurementMeta
    quality_score: int
    quality_label: str


@dataclass
class SeriesSummary:
    count: int = 0
    mean: float = 0.0
    median: float = 0.0
    spread: float = 0.0
    stability: int = 0
