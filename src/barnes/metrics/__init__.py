"""Metric computation (US-02): pure, no database — the caller supplies a scale.

Keeps the `io` computes / `db` persists / `cli` wires split (see CLAUDE.md):
this module never imports `barnes.db`. The CLI reads the montagem's scale via
`barnes.db.calibration`, calls the functions below with a plain `cm_per_px`,
then persists the result via `barnes.db.trial_results`.
"""

from __future__ import annotations

from collections.abc import Iterable
from itertools import pairwise
from math import fsum, hypot, isfinite

from barnes.io.calibration import Point, pixel_point, positive_number


def _nonnegative(value: float, name: str) -> float:
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{name} deve ser finito e não negativo.") from exc
    if isinstance(value, bool) or not isfinite(number) or number < 0:
        raise ValueError(f"{name} deve ser finito e não negativo.")
    return number


def _scaled(distance_px: float, cm_per_px: float) -> float:
    return _nonnegative(_nonnegative(distance_px, "Distância em pixels") * cm_per_px, "Distância")


def distance_cm(cm_per_px: float, distance_px: float) -> float:
    return _scaled(distance_px, cm_per_px)


def speed_cm_s(cm_per_px: float, distance_px: float, duration_s: float) -> float:
    distance = _scaled(distance_px, cm_per_px)
    return _nonnegative(distance / positive_number(duration_s, "Duração"), "Velocidade")


def _efficiency(ideal_cm: float, travelled_cm: float) -> float | None:
    if ideal_cm > travelled_cm + max(travelled_cm * 1e-12, 1e-12):
        raise ValueError("A distância ideal não pode exceder a distância percorrida.")
    if travelled_cm == 0:
        return None  # No route: efficiency is undefined, never fabricated as zero or one.
    return min(1.0, ideal_cm / travelled_cm)


def route_efficiency(cm_per_px: float, ideal_distance_px: float, travelled_distance_px: float) -> float | None:
    # Dimensionless, but intentionally requires calibration as specified by RN03.
    return _efficiency(_scaled(ideal_distance_px, cm_per_px), _scaled(travelled_distance_px, cm_per_px))


def process_trial(
    cm_per_px: float,
    points_px: Iterable[Point],
    timestamps_s: Iterable[float],
    *,
    frame_size: tuple[int, int],
    ideal_distance_px: float | None = None,
) -> dict[str, float | int | None]:
    """Calcula as métricas de uma trajetória já extraída (RN03).

    A extração de pose é uma história separada; as coordenadas em pixels
    devem se referir à resolução original do vídeo. Amostras ausentes devem
    ser tratadas por quem chama — são rejeitadas aqui, em vez de alterar
    silenciosamente a distância medida. Não persiste nada: quem chama grava
    o resultado via `barnes.db.trial_results.upsert_trial_result`.

    Args:
        cm_per_px: Escala da montagem (ver `barnes.db.calibration`).
        points_px: Pontos da trajetória, em pixels do quadro original.
        timestamps_s: Carimbo de tempo de cada ponto, em segundos.
        frame_size: Resolução (largura, altura) do quadro original — já
            deve ter sido confirmada contra a calibração por quem chama.
        ideal_distance_px: Distância ideal da rota, em pixels, se disponível.

    Returns:
        Um dicionário com `distance_cm`, `mean_speed_cm_s`, `duration_s`,
        `sample_count` e, se `ideal_distance_px` foi informado,
        `ideal_distance_cm` e `route_efficiency`.

    Raises:
        ValueError: Se houver menos de dois pontos, tempos não crescentes,
            contagens de pontos/tempos diferentes, ou coordenadas fora do
            quadro.
    """
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
    distance = _scaled(travelled_px, cm_per_px)
    duration = times[-1] - times[0]
    metrics: dict[str, float | int | None] = {
        "distance_cm": distance,
        "mean_speed_cm_s": _nonnegative(distance / duration, "Velocidade"),
        "duration_s": duration,
        "sample_count": len(points),
    }
    if ideal_distance_px is not None:
        ideal_cm = _scaled(ideal_distance_px, cm_per_px)
        metrics["ideal_distance_cm"] = ideal_cm
        metrics["route_efficiency"] = _efficiency(ideal_cm, distance)
    return metrics
