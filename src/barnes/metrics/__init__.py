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
from barnes.io.trim import TrialInterval, is_within_interval


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
    interval: TrialInterval,
    ideal_distance_px: float | None = None,
) -> dict[str, float | int | None]:
    """Calcula as métricas de uma trajetória já extraída (RN03).

    A extração de pose é uma história separada; as coordenadas em pixels
    devem se referir à resolução original do vídeo. Amostras ausentes devem
    ser tratadas por quem chama — são rejeitadas aqui, em vez de alterar
    silenciosamente a distância medida. Não persiste nada: quem chama grava
    o resultado via `barnes.db.trial_results.upsert_trial_result`.

    Só entram no cálculo as amostras dentro do intervalo útil do trial
    (US-03 RN02): `interval` é obrigatório justamente para que nenhum
    chamador calcule sobre a trajetória inteira por esquecimento. Um trecho
    que cruza a fronteira do intervalo não conta — a distância começa na
    primeira amostra de dentro.

    Args:
        cm_per_px: Escala da montagem (ver `barnes.db.calibration`).
        points_px: Pontos da trajetória, em pixels do quadro original.
        timestamps_s: Carimbo de tempo de cada ponto, em segundos **desde o
            início do arquivo de vídeo** (mesma referência de
            `TrialInterval.start_s`/`end_s`).
        frame_size: Resolução (largura, altura) do quadro original — já
            deve ter sido confirmada contra a calibração por quem chama.
        interval: Intervalo útil do trial (US-03).
        ideal_distance_px: Distância ideal da rota, em pixels, se disponível.

    Returns:
        Um dicionário com `distance_cm`, `mean_speed_cm_s`, `duration_s`,
        `sample_count` (amostras usadas), `samples_outside_interval`,
        `interval_start_s`/`interval_end_s` (auditoria, US-03 RN04) e, se
        `ideal_distance_px` foi informado, `ideal_distance_cm` e
        `route_efficiency`.

    Raises:
        ValueError: Se houver menos de dois pontos (no total ou dentro do
            intervalo útil), tempos não crescentes, contagens de
            pontos/tempos diferentes, ou coordenadas fora do quadro.
    """
    all_points = tuple(pixel_point(point) for point in points_px)
    all_times = tuple(_nonnegative(time, "Tempo") for time in timestamps_s)
    if len(all_points) < 2 or len(all_points) != len(all_times):
        raise ValueError("Forneça ao menos dois pontos, cada um com seu tempo em segundos.")
    width, height = frame_size
    if any(x >= width or y >= height for x, y in all_points):
        raise ValueError("A trajetória contém coordenadas fora do quadro original.")
    if any(end <= start for start, end in pairwise(all_times)):
        raise ValueError("Os tempos da trajetória devem ser estritamente crescentes.")

    inside = [
        (point, time)
        for point, time in zip(all_points, all_times, strict=True)
        if is_within_interval(time, interval)
    ]
    if len(inside) < 2:
        raise ValueError(
            f"Menos de duas amostras dentro do intervalo útil do trial "
            f"({interval.start_s:.2f}s a {interval.end_s:.2f}s). Confira se time_s é o tempo "
            "desde o início do vídeo e se o intervalo do trial está correto."
        )
    points = tuple(point for point, _ in inside)
    times = tuple(time for _, time in inside)
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
        "samples_outside_interval": len(all_points) - len(points),
        "interval_start_s": interval.start_s,
        "interval_end_s": interval.end_s,
    }
    if ideal_distance_px is not None:
        ideal_cm = _scaled(ideal_distance_px, cm_per_px)
        metrics["ideal_distance_cm"] = ideal_cm
        metrics["route_efficiency"] = _efficiency(ideal_cm, distance)
    return metrics
