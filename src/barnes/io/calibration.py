"""Scale calibration independent of OpenCV, the CLI and the database."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import asin, degrees, hypot, isclose, isfinite

Point = tuple[float, float]
MAX_RELATIVE_ERROR = 0.03
MIN_DIRECTION_ANGLE_DEGREES = 1.0


class CalibrationError(ValueError):
    """Invalid measurements or a scene incompatible with a single scalar."""


def positive_number(value: float, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CalibrationError(f"{name} deve ser um número finito e positivo.") from exc
    if isinstance(value, bool) or not isfinite(number) or number <= 0:
        raise CalibrationError(f"{name} deve ser um número finito e positivo.")
    return number


def pixel_point(point: Iterable[float]) -> Point:
    try:
        values = tuple(point)
        if len(values) != 2 or any(isinstance(value, bool) for value in values):
            raise ValueError
        x, y = (float(value) for value in values)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CalibrationError(
            "Cada ponto deve conter duas coordenadas válidas em pixels."
        ) from exc
    if not isfinite(x) or not isfinite(y) or x < 0 or y < 0:
        raise CalibrationError("As coordenadas devem ser finitas e não negativas.")
    return x, y


@dataclass(frozen=True)
class Segment:
    start: Point
    end: Point
    length_cm: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", pixel_point(self.start))
        object.__setattr__(self, "end", pixel_point(self.end))
        object.__setattr__(self, "length_cm", positive_number(self.length_cm, "Comprimento real"))
        positive_number(self.length_px, "Comprimento do segmento em pixels")

    @property
    def length_px(self) -> float:
        return hypot(self.end[0] - self.start[0], self.end[1] - self.start[1])

    @property
    def cm_per_px(self) -> float:
        return self.length_cm / self.length_px


@dataclass(frozen=True)
class CalibrationResult:
    segments: tuple[Segment, Segment]
    cm_per_px: float
    relative_disagreement: float
    angle_degrees: float


def _below_error_limit(error: float) -> bool:
    # An exactly 3% measurement must fail even after floating-point rounding.
    return error < MAX_RELATIVE_ERROR and not isclose(
        error, MAX_RELATIVE_ERROR, rel_tol=0, abs_tol=1e-12
    )


def calculate_calibration(segments: Iterable[Segment]) -> CalibrationResult:
    """Average two cm/px ratios after checking direction and consistency.

    The 3% inter-segment check detects incompatible scales; it does not replace
    the independent distance verification required by RN04. A scalar cannot
    correct perspective. Angles below one degree are treated as parallel.
    """
    segments = tuple(segments)
    if len(segments) != 2 or not all(isinstance(segment, Segment) for segment in segments):
        raise CalibrationError("A calibração exige exatamente dois segmentos conhecidos.")
    first, second = segments
    ux = (first.end[0] - first.start[0]) / first.length_px
    uy = (first.end[1] - first.start[1]) / first.length_px
    vx = (second.end[0] - second.start[0]) / second.length_px
    vy = (second.end[1] - second.start[1]) / second.length_px
    angle = degrees(asin(min(1.0, abs(ux * vy - uy * vx))))
    if angle < MIN_DIRECTION_ANGLE_DEGREES:
        raise CalibrationError(
            "Marque dois segmentos em direções diferentes (ângulo mínimo de 1 grau)."
        )
    scale_a = positive_number(first.cm_per_px, "Escala do segmento 1")
    scale_b = positive_number(second.cm_per_px, "Escala do segmento 2")
    scale = positive_number(scale_a / 2 + scale_b / 2, "Escala média")
    disagreement = abs(scale_a - scale_b) / scale
    if not _below_error_limit(disagreement):
        raise CalibrationError(
            f"Os segmentos divergem {disagreement:.2%} (limite: < 3%). "
            "Confira os pontos e comprimentos; pode haver distorção de perspectiva. "
            "Ajuste a câmera antes de calibrar novamente."
        )
    return CalibrationResult((first, second), scale, disagreement, angle)


@dataclass(frozen=True)
class VerificationResult:
    measured_cm: float
    known_cm: float
    relative_error: float
    accepted: bool


def verify_distance(calibration: CalibrationResult, independent: Segment) -> VerificationResult:
    """Check a third known distance, rejecting reuse of either calibration segment."""

    def same_point(a: Point, b: Point) -> bool:
        return all(isclose(x, y, rel_tol=0, abs_tol=1e-6) for x, y in zip(a, b))

    for segment in calibration.segments:
        forward = same_point(segment.start, independent.start) and same_point(
            segment.end, independent.end
        )
        reverse = same_point(segment.start, independent.end) and same_point(
            segment.end, independent.start
        )
        if forward or reverse:
            raise CalibrationError("Use uma terceira distância independente da calibração.")
    measured = positive_number(independent.length_px * calibration.cm_per_px, "Distância medida")
    error = abs(measured - independent.length_cm) / independent.length_cm
    return VerificationResult(measured, independent.length_cm, error, _below_error_limit(error))
