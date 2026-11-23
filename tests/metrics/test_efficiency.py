"""Índice de eficiência de rota (US-19): cálculo puro, sem banco nem vídeo."""

from __future__ import annotations

import math

import numpy as np
import pyarrow as pa
import pytest

from barnes.geometry.holes import generate_holes
from barnes.metrics.efficiency import (
    EXPORT_COLUMNS,
    SANITY_TOLERANCE,
    RouteEfficiencyError,
    compute_route_efficiency,
    compute_trial_route_efficiency,
    detect_release_point,
    route_efficiency_index,
    validate_route_efficiency,
)
from barnes.metrics.latency import CensoredMeasure, TargetEvent, compute_target_latencies

CM_PER_PX = 0.5
FPS = 25.0
STEP_S = 1.0 / FPS
TEMPO_LIMITE_S = 180.0

# Montagem sintética: plataforma centrada em (200, 200) px, buracos a 160 px (80 cm)
# do centro, 20 buracos, alvo = buraco 5 (90°, para baixo na imagem).
GEOMETRY = generate_holes(
    center_x_px=200.0,
    center_y_px=200.0,
    platform_radius_px=160.0,
    hole_count=20,
    start_angle_deg=0.0,
    target_hole_number=5,
    hole_radius_px=8.0,
)
CENTER_CM = (200.0 * CM_PER_PX, 200.0 * CM_PER_PX)
TARGET_CM = (GEOMETRY.target_hole.x_px * CM_PER_PX, GEOMETRY.target_hole.y_px * CM_PER_PX)
RADIUS_CM = 160.0 * CM_PER_PX
# O centro do corpo para alguns cm antes do buraco quando o focinho entra nele.
STOP_SHORT_CM = 3.0


def _table(points, *, valid=None) -> pa.Table:
    """Trajetória no formato do contrato (só as colunas usadas), um ponto por quadro."""
    xy = np.asarray(points, dtype=float)
    n = len(xy)
    valid = np.ones(n, dtype=bool) if valid is None else np.asarray(valid, dtype=bool)
    x = np.where(valid, xy[:, 0], np.nan)
    y = np.where(valid, xy[:, 1], np.nan)
    return pa.table(
        {
            "quadro": np.arange(100, 100 + n, dtype=np.int32),
            "t_s": np.arange(n) * STEP_S,
            "centro_corpo_x_cm_image": x,
            "centro_corpo_y_cm_image": y,
            "centro_corpo_valido": valid,
            "focinho_x_cm_image": x,
            "focinho_y_cm_image": y,
            "focinho_valido": valid,
            "base_cauda_x_cm_image": x,
            "base_cauda_y_cm_image": y,
            "base_cauda_valido": valid,
            "interpolado": np.zeros(n, dtype=bool),
            "fps_variavel": np.zeros(n, dtype=bool),
        }
    )


def _segment(a, b, frames: int) -> list[tuple[float, float]]:
    """`frames` pontos de a (exclusivo) até b (inclusivo), em linha reta."""
    return [
        (a[0] + (b[0] - a[0]) * i / frames, a[1] + (b[1] - a[1]) * i / frames)
        for i in range(1, frames + 1)
    ]


def _arc(angle_from_deg: float, angle_to_deg: float, radius: float, frames: int):
    angles = np.radians(np.linspace(angle_from_deg, angle_to_deg, frames + 1)[1:])
    return [
        (CENTER_CM[0] + radius * math.cos(a), CENTER_CM[1] + radius * math.sin(a)) for a in angles
    ]


def _short_of_target(from_point) -> tuple[float, float]:
    dx, dy = TARGET_CM[0] - from_point[0], TARGET_CM[1] - from_point[1]
    norm = math.hypot(dx, dy)
    return (TARGET_CM[0] - dx / norm * STOP_SHORT_CM, TARGET_CM[1] - dy / norm * STOP_SHORT_CM)


def _latencies(table: pa.Table, arrival_index: int | None, *, entry=True):
    t = None if arrival_index is None else float(table.column("t_s")[arrival_index].as_py())
    discovery = TargetEvent.nao_ocorreu() if t is None else TargetEvent.ocorreu(t)
    if entry:
        entry_event = TargetEvent.nao_ocorreu() if t is None else TargetEvent.ocorreu(t)
    else:
        entry_event = TargetEvent.nao_avaliado()
    return compute_target_latencies(table, discovery, entry_event, tempo_limite_s=TEMPO_LIMITE_S)


def _compute(table, arrival_index, **kwargs):
    return compute_trial_route_efficiency(
        table,
        _latencies(table, arrival_index, **kwargs),
        geometry=GEOMETRY,
        cm_per_px=CM_PER_PX,
    )


def _direct_route():
    """Soltura no centro e linha reta até o alvo (Cenário 1)."""
    arrival = _short_of_target(CENTER_CM)
    points = [CENTER_CM, *_segment(CENTER_CM, arrival, 50)]
    # Fica parado no buraco depois de chegar: não entra no índice.
    points += [arrival] * 10
    return points, 50


def _thigmotaxis_route():
    """Vai do centro até a borda no lado oposto e contorna a borda até o alvo (Cenário 2)."""
    border = RADIUS_CM - STOP_SHORT_CM
    start_border = (
        CENTER_CM[0] + border * math.cos(math.radians(270.0)),
        CENTER_CM[1] + border * math.sin(math.radians(270.0)),
    )
    points = [CENTER_CM, *_segment(CENTER_CM, start_border, 40)]
    # 270° → 90° pelo lado horário: 180° de borda, passando por 0° (direita da imagem).
    points += _arc(270.0, 450.0, border, 180)
    arrival_index = len(points) - 1
    points += [points[-1]] * 10
    return points, arrival_index


# --- Cenário 1: rota direta (SCRUM-234) ---------------------------------------------------


def test_scenario_1_direct_route_index_is_one_and_release_is_center():
    points, arrival = _direct_route()
    result = _compute(_table(points), arrival)

    assert result.soltura is not None
    assert result.soltura.x_cm_image == pytest.approx(CENTER_CM[0])
    assert result.soltura.y_cm_image == pytest.approx(CENTER_CM[1])
    assert result.soltura.t_s == 0.0
    assert result.soltura.quadro == 100
    assert result.soltura.distancia_centro_cm == pytest.approx(0.0, abs=1e-9)

    for measure in (result.primary, result.total):
        assert measure.evento == 1
        assert measure.indice == pytest.approx(1.0, abs=1e-9)
        assert measure.distancia_minima_cm == pytest.approx(RADIUS_CM - STOP_SHORT_CM)
        assert measure.distancia_soltura_alvo_cm == pytest.approx(RADIUS_CM)
        assert measure.avisos == ()


def test_index_uses_the_arrival_point_not_the_hole_center():
    # Contra o centro do buraco, a mesma rota reta daria índice < 1 (77 / 80).
    points, arrival = _direct_route()
    measure = _compute(_table(points), arrival).total
    assert measure.distancia_percorrida_cm / measure.distancia_soltura_alvo_cm < 1.0
    assert measure.indice >= 1.0


# --- Cenário 2: tigmotaxia (SCRUM-234) ----------------------------------------------------


def test_scenario_2_thigmotaxis_index_much_greater_than_one():
    points, arrival = _thigmotaxis_route()
    result = _compute(_table(points), arrival)
    measure = result.total
    border = RADIUS_CM - STOP_SHORT_CM
    expected_path = border + math.pi * border  # raio até a borda + meia volta
    expected_min = math.hypot(*(np.subtract(points[arrival], CENTER_CM)))
    assert measure.distancia_percorrida_cm == pytest.approx(expected_path, rel=1e-3)
    assert measure.distancia_minima_cm == pytest.approx(expected_min)
    assert measure.indice == pytest.approx(expected_path / expected_min, rel=1e-3)
    assert measure.indice > 3.0


# --- Cenário 3: censura (SCRUM-231) -------------------------------------------------------


def test_scenario_3_censored_trial_has_no_index_but_keeps_the_release_point():
    points, _ = _thigmotaxis_route()
    result = _compute(_table(points), None)
    for measure in (result.primary, result.total):
        assert measure.evento == 0
        assert measure.indice is None
        assert measure.distancia_minima_cm is None
        assert measure.latencia_s == TEMPO_LIMITE_S
        assert any("censurado" in aviso for aviso in measure.avisos)
    columns = result.as_trial_results()
    assert columns["primary_route_efficiency"] is None
    assert columns["total_route_efficiency"] is None
    assert columns["release_x_cm_image"] == pytest.approx(CENTER_CM[0])


def test_event_after_time_limit_is_censored_by_us16_and_has_no_index():
    points, arrival = _direct_route()
    table = _table(points)
    t = float(table.column("t_s")[arrival].as_py())
    latencies = compute_target_latencies(
        table, TargetEvent.ocorreu(t), TargetEvent.ocorreu(t), tempo_limite_s=t / 2
    )
    result = compute_trial_route_efficiency(table, latencies)
    assert result.primary.evento == 0
    assert result.primary.indice is None


def test_detector_not_run_is_not_censoring():
    points, arrival = _direct_route()
    result = _compute(_table(points), arrival, entry=False)
    assert result.primary.indice == pytest.approx(1.0, abs=1e-9)
    assert result.total.evento is None
    assert result.total.indice is None
    assert "não calculado" in result.total.avisos[0]


# --- Ponto de soltura (SCRUM-228) ---------------------------------------------------------


def test_release_point_is_detected_not_assumed_at_center():
    release = (CENTER_CM[0] - 20.0, CENTER_CM[1] - 10.0)
    arrival = _short_of_target(release)
    points = [release, *_segment(release, arrival, 60)]
    result = _compute(_table(points), len(points) - 1)
    assert result.soltura.x_cm_image == pytest.approx(release[0])
    assert result.soltura.y_cm_image == pytest.approx(release[1])
    assert result.soltura.distancia_centro_cm == pytest.approx(math.hypot(20.0, 10.0))
    assert result.total.indice == pytest.approx(1.0, abs=1e-9)
    assert result.total.distancia_soltura_alvo_cm == pytest.approx(
        math.hypot(TARGET_CM[0] - release[0], TARGET_CM[1] - release[1])
    )


def test_release_uses_first_valid_sample_and_warns_when_pose_is_missing_at_start():
    points, arrival = _direct_route()
    valid = np.ones(len(points), dtype=bool)
    valid[:5] = False
    result = _compute(_table(points, valid=valid), arrival)
    assert result.soltura.t_s == pytest.approx(5 * STEP_S)
    assert result.soltura.quadro == 105
    assert result.total.indice == pytest.approx(1.0, abs=1e-9)
    assert any("ausente no início" in aviso for aviso in result.total.avisos)


def test_no_valid_pose_means_unknown_release_and_no_index():
    points, _ = _direct_route()
    table = _table(points, valid=np.zeros(len(points), dtype=bool))
    assert detect_release_point(table) is None
    measure = compute_route_efficiency(
        table, CensoredMeasure(latency_s=1.0, distance_cm=None, event=1)
    )
    assert measure.indice is None
    assert "soltura" in measure.avisos[0]


def test_first_valid_pose_after_the_event_gives_no_index():
    points, _ = _direct_route()
    valid = np.ones(len(points), dtype=bool)
    valid[:30] = False
    measure = compute_route_efficiency(
        _table(points, valid=valid),
        CensoredMeasure(latency_s=10 * STEP_S, distance_cm=None, event=1),
    )
    assert measure.indice is None
    assert "até o evento" in measure.avisos[0]


def test_arrival_back_at_release_point_has_undefined_index():
    out = (CENTER_CM[0] + 10.0, CENTER_CM[1])
    points = [CENTER_CM, *_segment(CENTER_CM, out, 10), *_segment(out, CENTER_CM, 10)]
    measure = compute_route_efficiency(
        _table(points), CensoredMeasure(latency_s=20 * STEP_S, distance_cm=20.0, event=1)
    )
    assert measure.indice is None
    assert measure.distancia_minima_cm == 0
    assert any("mínima zero" in aviso for aviso in measure.avisos)


# --- Cenário 4: sanidade (SCRUM-233) ------------------------------------------------------


def test_scenario_4_index_below_one_fails_validation():
    with pytest.raises(RouteEfficiencyError, match="< 1,0"):
        route_efficiency_index(9.0, 10.0)
    with pytest.raises(RouteEfficiencyError, match="< 1,0"):
        validate_route_efficiency(0.999)


def test_sanity_tolerance_accepts_only_floating_point_rounding():
    assert validate_route_efficiency(1.0 - SANITY_TOLERANCE / 10) < 1.0
    with pytest.raises(RouteEfficiencyError):
        validate_route_efficiency(1.0 - SANITY_TOLERANCE * 10)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -1.0])
def test_invalid_distances_are_refused(bad):
    with pytest.raises(RouteEfficiencyError):
        route_efficiency_index(bad, 10.0)
    with pytest.raises(RouteEfficiencyError):
        validate_route_efficiency(math.nan)


def test_zero_minimum_distance_is_refused_by_the_raw_ratio():
    with pytest.raises(RouteEfficiencyError, match="mínima zero"):
        route_efficiency_index(5.0, 0.0)


@pytest.mark.parametrize("seed", range(20))
def test_any_processed_trial_has_index_at_least_one(seed):
    """Cenário 4 sobre trajetórias quaisquer: passeio aleatório, com lacunas de pose."""
    rng = np.random.default_rng(seed)
    n = 4500  # 180 s a 25 fps
    steps = rng.normal(0.0, 0.8, size=(n, 2))
    points = np.cumsum(steps, axis=0) + CENTER_CM
    valid = rng.random(n) > 0.1
    valid[0] = True
    table = _table(points, valid=valid)
    arrival = int(rng.integers(n // 2, n))
    latencies = _latencies(table, arrival)
    result = compute_trial_route_efficiency(table, latencies)
    assert result.total.indice is not None
    assert result.total.indice >= 1.0 - SANITY_TOLERANCE
    assert result.total.distancia_percorrida_cm == pytest.approx(latencies.total.distance_cm)


# --- Exportação (SCRUM-232) ---------------------------------------------------------------


def test_export_columns_carry_index_and_release_point():
    points, arrival = _direct_route()
    columns = _compute(_table(points), arrival).as_trial_results()
    assert tuple(columns) == EXPORT_COLUMNS
    assert columns["primary_route_efficiency"] == pytest.approx(1.0, abs=1e-9)
    assert columns["total_route_efficiency"] == pytest.approx(1.0, abs=1e-9)
    assert columns["release_x_cm_image"] == pytest.approx(CENTER_CM[0])
    assert columns["release_y_cm_image"] == pytest.approx(CENTER_CM[1])
    assert columns["release_t_s"] == 0.0
    assert columns["release_center_distance_cm"] == pytest.approx(0.0, abs=1e-9)


def test_release_center_distance_needs_geometry():
    points, arrival = _direct_route()
    table = _table(points)
    result = compute_trial_route_efficiency(table, _latencies(table, arrival))
    assert result.soltura.distancia_centro_cm is None
    assert result.total.distancia_soltura_alvo_cm is None
    assert result.total.indice == pytest.approx(1.0, abs=1e-9)


# --- Entradas inválidas ------------------------------------------------------------------


def test_geometry_and_scale_go_together():
    points, _ = _direct_route()
    with pytest.raises(ValueError, match="juntas"):
        detect_release_point(_table(points), geometry=GEOMETRY)


def test_unknown_point_is_refused():
    points, _ = _direct_route()
    with pytest.raises(ValueError, match="desconhecido"):
        detect_release_point(_table(points), ponto="orelha")


def test_release_measured_with_another_point_is_refused():
    points, _ = _direct_route()
    table = _table(points)
    release = detect_release_point(table, ponto="focinho")
    with pytest.raises(ValueError, match="focinho"):
        compute_route_efficiency(
            table, CensoredMeasure(latency_s=1.0, distance_cm=1.0, event=1), release=release
        )
