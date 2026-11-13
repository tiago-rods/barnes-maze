"""Distância total e velocidade média (US-18): cálculo puro, sem banco nem vídeo."""

from __future__ import annotations

import numpy as np
import pyarrow as pa
import pytest

from barnes.io.trim import interval_from_seconds
from barnes.metrics.displacement import (
    EXPORT_COLUMNS,
    SPEED_FPS_CAVEAT,
    compute_displacement,
)
from barnes.pose.annotations import KEYPOINTS
from barnes.pose.quality import QualityParams, postprocess_pose
from barnes.pose.series import PoseFrames, build_series
from barnes.pose.trajectory import read_trajectory, write_trajectory


def _trajectory(
    *, end_s=10.0, step_s=1.0, speed_cm_s=2.0, valid=None, interpolated=None, fps_variavel=False
):
    """Linha reta em x a velocidade constante, com `t_s` desde o início do intervalo."""
    t_s = np.arange(0.0, end_s + step_s / 2, step_s)
    n = t_s.size
    x = speed_cm_s * t_s
    valid = np.ones(n, dtype=bool) if valid is None else np.asarray(valid, dtype=bool)
    interpolated = (
        np.zeros(n, dtype=bool) if interpolated is None else np.asarray(interpolated, dtype=bool)
    )
    x = np.where(valid, x, np.nan)
    y = np.where(valid, 0.0, np.nan)
    return pa.table(
        {
            "t_s": t_s,
            "centro_corpo_x_cm_image": x,
            "centro_corpo_y_cm_image": y,
            "centro_corpo_valido": valid,
            "focinho_x_cm_image": x + 2.0,
            "focinho_y_cm_image": y,
            "focinho_valido": valid,
            "base_cauda_x_cm_image": x - 2.0,
            "base_cauda_y_cm_image": y,
            "base_cauda_valido": valid,
            "interpolado": interpolated,
            "fps_variavel": np.full(n, fps_variavel),
        }
    )


# --- Cenário 1: uma distância e uma velocidade por trial (SCRUM-219/220) -----------------


def test_scenario_1_distance_in_cm_and_mean_speed_in_cm_s():
    result = compute_displacement(_trajectory(end_s=10.0, speed_cm_s=2.0))
    assert result.distance_cm == pytest.approx(20.0)
    assert result.mean_speed_cm_s == pytest.approx(2.0)
    assert result.duration_s == pytest.approx(10.0)
    assert result.interval_duration_s == pytest.approx(10.0)
    assert result.edge_gap_s == 0
    assert result.frames_used == result.frames_total == 11
    assert result.ponto == "centro_corpo"
    assert result.speed_caveat is None
    assert result.avisos == ()


def test_distance_follows_the_path_not_the_displacement():
    # Vai 5 cm e volta 5 cm: percorreu 10 cm, mesmo terminando onde começou.
    table = _trajectory(end_s=2.0, step_s=1.0)
    x = pa.array([0.0, 5.0, 0.0])
    table = table.set_column(table.schema.get_field_index("centro_corpo_x_cm_image"),
                             "centro_corpo_x_cm_image", x)
    result = compute_displacement(table)
    assert result.distance_cm == pytest.approx(10.0)
    assert result.mean_speed_cm_s == pytest.approx(5.0)


def test_other_body_point_can_be_chosen():
    table = _trajectory(end_s=4.0, speed_cm_s=1.0)
    assert compute_displacement(table, ponto="focinho").distance_cm == pytest.approx(4.0)


def test_unknown_point_is_refused():
    with pytest.raises(ValueError, match="desconhecido"):
        compute_displacement(_trajectory(), ponto="orelha")


def test_trajectory_without_interpolation_column_is_refused():
    table = _trajectory().drop(["interpolado"])
    with pytest.raises(ValueError, match="interpolado"):
        compute_displacement(table)


# --- Duração: primeiro ao último ponto válido (SCRUM-220) --------------------------------


def test_edge_gap_is_excluded_from_the_speed_duration_and_reported():
    # Sem pose nos 2 primeiros e no último segundo: velocidade continua a real (2 cm/s).
    valid = [False, False, True, True, True, True, True, True, True, True, False]
    result = compute_displacement(_trajectory(end_s=10.0, speed_cm_s=2.0, valid=valid))
    assert result.duration_s == pytest.approx(7.0)
    assert result.interval_duration_s == pytest.approx(10.0)
    assert result.edge_gap_s == pytest.approx(3.0)
    assert result.distance_cm == pytest.approx(14.0)
    assert result.mean_speed_cm_s == pytest.approx(2.0)
    assert any("bordas" in aviso for aviso in result.avisos)


def test_interior_gap_is_bridged_in_a_straight_line_and_warned():
    valid = [True, True, True, False, False, True, True]
    result = compute_displacement(_trajectory(end_s=6.0, speed_cm_s=1.0, valid=valid))
    assert result.distance_cm == pytest.approx(6.0)  # reta 2 → 5 cobre os quadros ausentes
    assert result.duration_s == pytest.approx(6.0)
    assert any("2 quadro(s)" in aviso for aviso in result.avisos)


# --- Ausência não vira zero ---------------------------------------------------------------


def test_no_valid_sample_gives_none_never_zero():
    result = compute_displacement(_trajectory(end_s=3.0, valid=[False] * 4))
    assert result.distance_cm is None
    assert result.mean_speed_cm_s is None
    assert result.duration_s is None
    assert result.interpolated_fraction is None
    assert result.frames_used == 0
    assert result.as_export_columns()["path_distance"] is None
    assert any("ausência não é zero" in aviso for aviso in result.avisos)


def test_single_valid_sample_has_zero_distance_and_no_speed():
    result = compute_displacement(_trajectory(end_s=3.0, valid=[False, True, False, False]))
    assert result.distance_cm == 0
    assert result.mean_speed_cm_s is None
    assert any("uma amostra" in aviso for aviso in result.avisos)


def test_empty_trajectory_is_refused():
    with pytest.raises(ValueError, match="vazia"):
        compute_displacement(_trajectory().slice(0, 0))


# --- Fração interpolada (SCRUM-221, RN05) -------------------------------------------------


def test_interpolated_rows_enter_the_distance_and_the_fraction_is_reported():
    interpolated = [False, False, True, True, False, False, False, False, False, False, False]
    result = compute_displacement(_trajectory(end_s=10.0, interpolated=interpolated))
    assert result.distance_cm == pytest.approx(20.0)  # entram no cálculo
    assert result.interpolated_fraction == pytest.approx(2 / 11)


def test_fraction_counts_only_samples_used_in_the_distance():
    valid = [True, True, True, False]
    interpolated = [False, True, False, False]
    result = compute_displacement(_trajectory(end_s=3.0, valid=valid, interpolated=interpolated))
    assert result.interpolated_fraction == pytest.approx(1 / 3)


# --- Cenário 3: fps variável (SCRUM-222, RN07) --------------------------------------------


def test_scenario_3_variable_fps_keeps_distance_and_flags_only_the_speed():
    constant = compute_displacement(_trajectory(fps_variavel=False))
    variable = compute_displacement(_trajectory(fps_variavel=True))
    assert variable.distance_cm == constant.distance_cm
    assert variable.mean_speed_cm_s == constant.mean_speed_cm_s
    assert variable.fps_variavel is True
    assert variable.speed_caveat == SPEED_FPS_CAVEAT
    assert "velocidade" in variable.speed_caveat and "distância não" in variable.speed_caveat
    assert constant.speed_caveat is None
    assert variable.as_export_columns()["speed_time_base_approx"] is True
    assert constant.as_export_columns()["speed_time_base_approx"] is False


# --- Colunas da US-25 (SCRUM-224) ---------------------------------------------------------


def test_export_columns_are_the_complementary_trials_csv_columns():
    columns = compute_displacement(_trajectory()).as_export_columns()
    assert tuple(columns) == EXPORT_COLUMNS
    # Nunca colide com as colunas do laboratório (total_distance é S→E, US-16).
    assert not set(columns) & {"primary_distance", "delta_distance", "total_distance"}
    assert columns == {
        "path_distance": pytest.approx(20.0),
        "mean_speed": pytest.approx(2.0),
        "interpolated_fraction": 0.0,
        "speed_time_base_approx": False,
    }


# --- Série real do contrato (US-09 + US-10) -----------------------------------------------


def test_contract_series_with_us10_interpolation(tmp_path):
    """Série escrita e relida pelo contrato, com uma lacuna curta interpolada pela US-10."""
    fps, first, n = 10.0, 100, 11
    rows = np.arange(n)
    offsets = {"focinho": 20.0, "centro_corpo": 0.0, "base_cauda": -20.0}
    x = {p: 100.0 + 10.0 * rows + offsets[p] for p in KEYPOINTS}  # 10 px/quadro
    y = {p: np.full(n, 50.0) for p in KEYPOINTS}
    confidence = {p: np.full(n, 0.9) for p in KEYPOINTS}
    for point in KEYPOINTS:  # quadros 104-105 sem nenhum ponto: lacuna curta
        x[point][[4, 5]] = np.nan
        y[point][[4, 5]] = np.nan
        confidence[point][[4, 5]] = np.nan
    params = QualityParams(
        min_coverage=0.5, short_gap_max_frames=5, smoothing_method="mediana", smoothing_window=1
    )
    processed = postprocess_pose(PoseFrames(first + rows, x, y, confidence), params)
    table = build_series(
        processed.pose,
        trial_id=1,
        execucao_id=2,
        expected_frames=(first, first + n - 1),
        fps=fps,
        interval=interval_from_seconds(first / fps, (first + n - 1) / fps, fps,
                                       manually_adjusted=True),
        fps_variable=True,
        cm_per_px=0.1,
        content_hash="a" * 64,
        model_id="teste",
        interpolated=processed.interpolated,
        postprocessing=processed.report,
    )
    table = read_trajectory(write_trajectory(table, tmp_path / "trial_1.parquet"))

    result = compute_displacement(table)
    assert result.distance_cm == pytest.approx(10.0)  # 100 px · 0,1 cm/px
    assert result.duration_s == pytest.approx(1.0)
    assert result.mean_speed_cm_s == pytest.approx(10.0)
    assert result.interpolated_fraction == pytest.approx(2 / 11)
    assert result.speed_caveat == SPEED_FPS_CAVEAT
