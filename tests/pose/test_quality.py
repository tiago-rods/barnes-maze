"""Qualidade da pose (US-10, SCRUM-125..130/134): suavização, lacunas, cobertura, correções.

Sem banco, GPU nem janela: pose sintética em pixels, com o animal andando em linha
reta para a direita (2 px por quadro), o que torna exato o valor esperado de uma
interpolação linear.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from barnes.io.trim import interval_from_seconds
from barnes.pose.annotations import KEYPOINTS
from barnes.pose.quality import (
    FPS_VARIABLE_CAVEAT,
    FlaggedSegment,
    PointCorrection,
    PoseQuality,
    QualityConfigError,
    QualityParams,
    apply_corrections,
    classify,
    find_gaps,
    flag_long_gaps,
    interpolate_short_gaps,
    load_quality_params,
    pose_coverage,
    postprocess_pose,
    segments_from_report,
    smooth_points,
)
from barnes.pose.series import PoseFrames, SeriesError, build_series
from barnes.pose.trajectory import (
    POSTPROCESSING_KEY,
    TrajectoryContractError,
    read_metadata,
    read_trajectory,
    write_trajectory,
)

FIRST_FRAME = 100
FPS = 10.0
OFFSETS = {"focinho": 20.0, "centro_corpo": 0.0, "base_cauda": -20.0}
SNOUT, CENTER, TAIL = KEYPOINTS

# Sem suavização por padrão: os testes de lacuna medem só a interpolação.
PARAMS = QualityParams(
    min_coverage=0.98, short_gap_max_frames=5, smoothing_method="mediana", smoothing_window=1
)


def _expected_x(point, rows):
    return 100.0 + 2.0 * np.asarray(rows, dtype=float) + OFFSETS[point]


def _pose(n=20, missing=None):
    """`missing`: {ponto: linhas (posição na série) sem o ponto}."""
    rows = np.arange(n)
    x = {p: _expected_x(p, rows) for p in KEYPOINTS}
    y = {p: np.full(n, 50.0) for p in KEYPOINTS}
    confidence = {p: np.full(n, 0.9) for p in KEYPOINTS}
    for point, gone in (missing or {}).items():
        x[point][list(gone)] = np.nan
        y[point][list(gone)] = np.nan
        confidence[point][list(gone)] = np.nan
    return PoseFrames(FIRST_FRAME + rows, x, y, confidence)


def _rows(start, end):
    return list(range(start, end + 1))


# --- Lacunas ---------------------------------------------------------------------


def test_find_gaps_reports_runs_and_edges():
    valid = np.array([False, True, True, False, False, True, False])
    gaps = find_gaps(valid)
    assert [(g.start, g.end, g.at_edge, g.length) for g in gaps] == [
        (0, 0, True, 1),
        (3, 4, False, 2),
        (6, 6, True, 1),
    ]
    assert find_gaps(np.ones(4, bool)) == []


# --- Cenário 1: lacuna curta interpolada (SCRUM-128) -------------------------------


def test_short_interior_gap_is_interpolated_marked_and_needs_no_review():
    pose = _pose(missing={SNOUT: _rows(5, 7)})
    result = postprocess_pose(pose, PARAMS)

    assert result.pose.x_px[SNOUT][5:8] == pytest.approx(_expected_x(SNOUT, [5, 6, 7]))
    assert result.pose.y_px[SNOUT][5:8] == pytest.approx([50.0] * 3)
    assert np.flatnonzero(result.interpolated).tolist() == [5, 6, 7]
    assert result.segments == ()
    assert result.quality is PoseQuality.SUFICIENTE
    assert result.report["quadros_interpolados"] == 3
    assert result.report["cobertura"] == pytest.approx(1.0)
    assert result.report["cobertura_deteccao"] == pytest.approx(17 / 20)
    # A confiança do modelo não é inventada para o quadro preenchido.
    assert np.isnan(result.pose.confidence[SNOUT][5:8]).all()


@pytest.mark.parametrize(("length", "interpolated"), [(5, True), (6, False)])
def test_gap_at_the_limit_is_interpolated_and_one_more_frame_is_flagged(length, interpolated):
    pose = _pose(missing={SNOUT: _rows(4, 4 + length - 1)})
    filled, mask = interpolate_short_gaps(pose, max_frames=5)
    assert bool(mask.any()) is interpolated
    flagged = flag_long_gaps(filled, max_frames=5)
    assert bool(flagged) is not interpolated


def test_gap_only_in_tail_base_fills_only_that_point():
    pose = _pose(missing={TAIL: _rows(8, 9)})
    filled, mask = interpolate_short_gaps(pose, max_frames=5)
    assert filled.x_px[TAIL][8:10] == pytest.approx(_expected_x(TAIL, [8, 9]))
    assert filled.x_px[SNOUT] == pytest.approx(pose.x_px[SNOUT])
    assert np.flatnonzero(mask).tolist() == [8, 9]


# --- Cenário 2 (parte pura): lacuna longa sinalizada (SCRUM-129) -------------------


def test_long_gap_is_flagged_and_not_interpolated():
    pose = _pose(missing={CENTER: _rows(4, 13)})
    result = postprocess_pose(pose, PARAMS)

    assert np.isnan(result.pose.x_px[CENTER][4:14]).all()
    assert not result.interpolated.any()
    assert result.segments == (FlaggedSegment(104, 113, (CENTER,), pending=True),)
    assert result.quality is PoseQuality.REVISAO_PENDENTE
    assert result.report["trechos_pendentes"] == 1
    assert result.report["trechos_sinalizados"] == [
        {"inicio": 104, "fim": 113, "pontos": [CENTER], "pendente": True}
    ]


def test_edge_gap_is_flagged_even_when_short():
    pose = _pose(missing={TAIL: _rows(0, 1)})
    result = postprocess_pose(pose, PARAMS)
    assert not result.interpolated.any()
    assert result.segments == (FlaggedSegment(100, 101, (TAIL,)),)


def test_overlapping_gaps_of_different_points_become_one_segment():
    pose = _pose(missing={SNOUT: _rows(3, 10), TAIL: _rows(9, 15)})
    segments = flag_long_gaps(pose, max_frames=5)
    assert segments == [FlaggedSegment(103, 115, (SNOUT, TAIL))]


def test_segments_round_trip_through_the_report():
    result = postprocess_pose(_pose(missing={SNOUT: _rows(2, 12)}), PARAMS)
    assert tuple(segments_from_report(result.report)) == result.segments


# --- Suavização (SCRUM-126) --------------------------------------------------------


def test_smoothing_keeps_straight_motion_exactly():
    pose = _pose()
    smoothed = smooth_points(pose, window=5)
    for point in KEYPOINTS:
        assert smoothed.x_px[point] == pytest.approx(pose.x_px[point])


def test_smoothing_removes_an_isolated_spike():
    pose = _pose()
    pose.x_px[SNOUT][10] += 30.0  # troca momentânea de ponto
    smoothed = smooth_points(pose, window=5)
    # Numa reta, a mediana tira o pico e erra no máximo um passo (2 px) em volta dele.
    error = np.abs(smoothed.x_px[SNOUT] - _expected_x(SNOUT, range(20)))
    assert error.max() <= 2.0
    assert error[10] <= 2.0  # o pico era de 30 px


def test_smoothing_never_fills_nor_crosses_a_gap():
    pose = _pose(missing={SNOUT: [10]})
    pose.x_px[SNOUT][9] += 30.0  # pico logo antes da lacuna: a janela encolhe, não atravessa
    smoothed = smooth_points(pose, window=5)
    assert math.isnan(smoothed.x_px[SNOUT][10])
    # O ponto de apoio da interpolação (linha 11, borda do trecho) fica intacto.
    assert smoothed.x_px[SNOUT][11] == pytest.approx(_expected_x(SNOUT, [11])[0])


def test_window_one_is_identity_and_even_window_is_refused():
    pose = _pose()
    assert smooth_points(pose, window=1) is pose
    with pytest.raises(ValueError, match="ímpar"):
        smooth_points(pose, window=4)


def test_theta_is_recomputed_from_smoothed_points():
    pose = _pose()
    pose.y_px[SNOUT][10] += 15.0  # focinho "pula" para baixo num quadro só
    params = QualityParams(0.98, 5, "mediana", 5)
    table = _series(postprocess_pose(pose, params))
    assert table.column("theta_deg_image").to_pylist() == pytest.approx([0.0] * 20)


# --- Cobertura (SCRUM-130) e Cenário 3 ---------------------------------------------


def test_coverage_counts_three_points_and_interpolated_frames():
    pose = _pose(n=100, missing={TAIL: _rows(40, 49), SNOUT: [70, 71]})
    assert pose_coverage(pose) == pytest.approx(88 / 100)
    result = postprocess_pose(pose, PARAMS)
    assert result.report["cobertura_deteccao"] == pytest.approx(0.88)
    assert result.report["cobertura"] == pytest.approx(0.90)  # 2 interpolados contam


def test_coverage_of_empty_pose_is_undefined():
    empty = PoseFrames(np.array([], dtype=np.int64), *({p: np.array([]) for p in KEYPOINTS},) * 3)
    with pytest.raises(ValueError, match="nenhum quadro"):
        pose_coverage(empty)


def test_reviewed_trial_below_minimum_is_insufficient():
    # Cenário 3: 7 quadros sem focinho em 100, revisados sem correção → 0,93.
    pose = _pose(n=100, missing={SNOUT: _rows(40, 46)})
    result = postprocess_pose(pose, PARAMS, reviewed_ranges=[(140, 146)])
    assert result.report["cobertura"] == pytest.approx(0.93)
    assert result.segments == (FlaggedSegment(140, 146, (SNOUT,), pending=False),)
    assert result.quality is PoseQuality.INSUFICIENTE


def test_unreviewed_or_partially_reviewed_gap_keeps_review_pending():
    pose = _pose(n=100, missing={SNOUT: _rows(40, 46)})
    assert postprocess_pose(pose, PARAMS).quality is PoseQuality.REVISAO_PENDENTE
    partial = postprocess_pose(pose, PARAMS, reviewed_ranges=[(140, 143)])
    assert partial.quality is PoseQuality.REVISAO_PENDENTE


@pytest.mark.parametrize(
    ("coverage", "pending", "expected"),
    [
        (0.99, 0, PoseQuality.SUFICIENTE),
        (0.98, 0, PoseQuality.SUFICIENTE),
        (0.93, 0, PoseQuality.INSUFICIENTE),
        (0.93, 1, PoseQuality.REVISAO_PENDENTE),
        (1.0, 1, PoseQuality.REVISAO_PENDENTE),
    ],
)
def test_classify(coverage, pending, expected):
    assert classify(coverage, 0.98, pending) is expected


# --- Correções manuais (SCRUM-132, parte pura) -------------------------------------


def test_correction_fills_the_point_and_the_latest_one_wins():
    pose = _pose(missing={SNOUT: [3]})
    corrected, mask = apply_corrections(
        pose,
        [PointCorrection(103, SNOUT, 1.0, 2.0), PointCorrection(103, SNOUT, 7.0, 8.0)],
    )
    assert (corrected.x_px[SNOUT][3], corrected.y_px[SNOUT][3]) == (7.0, 8.0)
    assert np.flatnonzero(mask).tolist() == [3]
    assert math.isnan(corrected.confidence[SNOUT][3])
    assert math.isnan(pose.x_px[SNOUT][3])  # a pose de entrada não é alterada


def test_sparse_corrections_turn_a_long_gap_into_short_interpolated_ones():
    pose = _pose(missing={SNOUT: _rows(2, 15)})
    marks = [PointCorrection(FIRST_FRAME + row, SNOUT, _expected_x(SNOUT, [row])[0], 50.0)
             for row in (7, 11)]
    result = postprocess_pose(pose, PARAMS, corrections=marks)
    assert result.segments == ()
    assert result.report["cobertura"] == pytest.approx(1.0)
    assert result.report["quadros_corrigidos"] == 2
    assert result.pose.x_px[SNOUT] == pytest.approx(_expected_x(SNOUT, range(20)))


def test_corrections_outside_the_series_are_ignored_and_counted():
    result = postprocess_pose(_pose(), PARAMS, corrections=[PointCorrection(5, SNOUT, 1.0, 1.0)])
    assert result.report["correcoes_ignoradas"] == 1
    with pytest.raises(ValueError, match="fora da série"):
        apply_corrections(_pose(), [PointCorrection(5, SNOUT, 1.0, 1.0)])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"frame": -1, "point": SNOUT, "x_px": 1.0, "y_px": 1.0},
        {"frame": 1, "point": "orelha", "x_px": 1.0, "y_px": 1.0},
        {"frame": 1, "point": SNOUT, "x_px": math.nan, "y_px": 1.0},
        {"frame": 1, "point": SNOUT, "x_px": 1.0, "y_px": -2.0},
    ],
)
def test_point_correction_rejects_invalid_values(kwargs):
    with pytest.raises(ValueError):
        PointCorrection(**kwargs)


# --- RN07: fps variável ------------------------------------------------------------


def test_interpolation_on_variable_fps_carries_the_caveat():
    pose = _pose(missing={SNOUT: [5]})
    assert postprocess_pose(pose, PARAMS, fps_variable=True).report[
        "ressalva_fps_variavel"
    ] == FPS_VARIABLE_CAVEAT
    assert postprocess_pose(pose, PARAMS).report["ressalva_fps_variavel"] is None
    assert postprocess_pose(_pose(), PARAMS, fps_variable=True).report[
        "ressalva_fps_variavel"
    ] is None


# --- Configuração (SCRUM-125) ------------------------------------------------------


def test_default_config_has_the_group_proposed_values():
    params = load_quality_params()
    assert params == QualityParams(0.98, 5, "mediana", 5)


def _config(tmp_path, body):
    path = tmp_path / "default.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _pose_section(*, minimum="0.98", gap="5", method="mediana", window="5"):
    return "\n".join([
        "pose:",
        f"  cobertura_minima: {minimum}",
        f"  lacuna_curta_max_quadros: {gap}",
        f"  suavizacao: {{metodo: {method}, janela_quadros: {window}}}",
        "",
    ])


def test_null_value_is_refused_naming_the_key(tmp_path):
    path = _config(tmp_path, _pose_section(gap="null"))
    with pytest.raises(QualityConfigError, match="pose.lacuna_curta_max_quadros"):
        load_quality_params(path)


@pytest.mark.parametrize(
    ("body", "key"),
    [
        ("anotacao: {}", "Seção 'pose'"),
        (_pose_section(window="4"), "janela_quadros"),
        (_pose_section(minimum="1.5"), "cobertura_minima"),
        (_pose_section(gap="2.5"), "lacuna_curta_max_quadros"),
        (_pose_section(method="media"), "metodo"),
    ],
)
def test_invalid_config_is_refused(tmp_path, body, key):
    with pytest.raises(QualityConfigError, match=key):
        load_quality_params(_config(tmp_path, body))


# --- Contrato da série (SCRUM-127) -------------------------------------------------


def _series(result, *, postprocessing=True, interpolated=None):
    n = len(result.pose.frames)
    return build_series(
        result.pose,
        trial_id=3,
        execucao_id=9,
        expected_frames=(FIRST_FRAME, FIRST_FRAME + n - 1),
        fps=FPS,
        interval=interval_from_seconds(
            FIRST_FRAME / FPS, (FIRST_FRAME + n - 1) / FPS, FPS, manually_adjusted=True
        ),
        fps_variable=False,
        cm_per_px=0.5,
        content_hash="a" * 64,
        model_id="modelo-teste",
        interpolated=result.interpolated if interpolated is None else interpolated,
        postprocessing=result.report if postprocessing else None,
    )


def test_postprocessed_series_meets_the_contract_and_keeps_the_report(tmp_path):
    result = postprocess_pose(_pose(missing={SNOUT: [5], CENTER: _rows(12, 19)}), PARAMS)
    path = write_trajectory(_series(result), tmp_path / "trial_3.parquet")
    table = read_trajectory(path)
    data = table.to_pydict()
    assert data["interpolado"][5] is True and sum(data["interpolado"]) == 1
    assert data["focinho_valido"][5] is True and data["pose_valida"][5] is True
    assert data["centro_corpo_valido"][12] is False and data["pose_valida"][12] is False
    report = read_metadata(table)[POSTPROCESSING_KEY]
    assert report["qualidade"] == "revisao_pendente"
    assert report["trechos_sinalizados"][0]["inicio"] == 112


def test_interpolated_rows_without_the_report_are_refused():
    result = postprocess_pose(_pose(missing={SNOUT: [5]}), PARAMS)
    with pytest.raises(TrajectoryContractError, match=POSTPROCESSING_KEY):
        _series(result, postprocessing=False)


def test_interpolation_mask_must_have_one_entry_per_frame():
    result = postprocess_pose(_pose(), PARAMS)
    with pytest.raises(SeriesError, match="máscara"):
        _series(result, interpolated=np.zeros(3, dtype=bool))
