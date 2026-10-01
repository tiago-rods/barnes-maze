"""Metric entry points: every conversion requires a persisted camera scale."""

from __future__ import annotations

from collections.abc import Iterable
from itertools import pairwise
from math import fsum, hypot, isfinite

from barnes.db import CalibrationRepository, StoredCalibration, StoredExecution
from barnes.io.calibration import Point, pixel_point, positive_number


def _nonnegative(value: float, name: str) -> float:
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{name} deve ser finito e não negativo.") from exc
    if isinstance(value, bool) or not isfinite(number) or number < 0:
        raise ValueError(f"{name} deve ser finito e não negativo.")
    return number


def _scaled(distance_px: float, scale: float) -> float:
    return _nonnegative(_nonnegative(distance_px, "Distância em pixels") * scale, "Distância")


def distance_cm(
    repository: CalibrationRepository, orientation_id: str, distance_px: float
) -> float:
    calibration = repository.require_calibration(orientation_id)
    return _scaled(distance_px, calibration.result.cm_per_px)


def speed_cm_s(
    repository: CalibrationRepository, orientation_id: str, distance_px: float, duration_s: float
) -> float:
    calibration = repository.require_calibration(orientation_id)
    distance = _scaled(distance_px, calibration.result.cm_per_px)
    return _nonnegative(distance / positive_number(duration_s, "Duração"), "Velocidade")


def _efficiency(ideal_cm: float, travelled_cm: float) -> float | None:
    if ideal_cm > travelled_cm + max(travelled_cm * 1e-12, 1e-12):
        raise ValueError("A distância ideal não pode exceder a distância percorrida.")
    if travelled_cm == 0:
        return None  # No route: efficiency is undefined, never fabricated as zero or one.
    return min(1.0, ideal_cm / travelled_cm)


def route_efficiency(
    repository: CalibrationRepository,
    orientation_id: str,
    ideal_distance_px: float,
    travelled_distance_px: float,
) -> float | None:
    # Dimensionless, but intentionally requires calibration as specified by RN03.
    calibration = repository.require_calibration(orientation_id)
    factor = calibration.result.cm_per_px
    return _efficiency(_scaled(ideal_distance_px, factor), _scaled(travelled_distance_px, factor))


def validate_frame_size(calibration: StoredCalibration, frame_size: tuple[int, int]) -> None:
    if tuple(frame_size) != calibration.reference_size:
        raise ValueError(
            f"Resolução {frame_size} diferente da calibração {calibration.reference_size}. "
            "Use as coordenadas originais e calibre uma nova orientação para esta resolução."
        )


def process_trial(
    repository: CalibrationRepository,
    trial_id: str,
    orientation_id: str,
    points_px: Iterable[Point],
    timestamps_s: Iterable[float],
    *,
    frame_size: tuple[int, int],
    ideal_distance_px: float | None = None,
) -> StoredExecution:
    """Process a supplied trajectory with one recorded scale snapshot.

    Pose extraction is a separate story. Pixel coordinates must refer to the
    original video resolution. Missing samples must be handled upstream; they
    are rejected here instead of silently changing measured path length.
    """
    calibration = repository.require_calibration(orientation_id)
    validate_frame_size(calibration, frame_size)
    points = tuple(pixel_point(point) for point in points_px)
    times = tuple(_nonnegative(time, "Tempo") for time in timestamps_s)
    if len(points) < 2 or len(points) != len(times):
        raise ValueError("Forneça ao menos dois pontos, cada um com seu tempo em segundos.")
    width, height = frame_size
    if any(x >= width or y >= height for x, y in points):
        raise ValueError("A trajetória contém coordenadas fora do quadro original.")
    if any(end <= start for start, end in pairwise(times)):
        raise ValueError("Os tempos da trajetória devem ser estritamente crescentes.")
    travelled_px = fsum(
        hypot(end[0] - start[0], end[1] - start[1]) for start, end in pairwise(points)
    )
    distance = _scaled(travelled_px, calibration.result.cm_per_px)
    duration = times[-1] - times[0]
    metrics = {
        "distance_cm": distance,
        "mean_speed_cm_s": _nonnegative(distance / duration, "Velocidade"),
        "duration_s": duration,
        "sample_count": len(points),
    }
    if ideal_distance_px is not None:
        ideal_cm = _scaled(ideal_distance_px, calibration.result.cm_per_px)
        metrics["ideal_distance_cm"] = ideal_cm
        metrics["route_efficiency"] = _efficiency(ideal_cm, distance)
    # The repository rejects this write if a recalibration happened during calculation.
    return repository.record_execution(trial_id, calibration.id, metrics)
