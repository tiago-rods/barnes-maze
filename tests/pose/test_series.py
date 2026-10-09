"""Série (x, y, θ, t) a partir da pose inferida (US-09, SCRUM-117/118/119/121/122).

Sem banco nem GPU: escala fixa injetada e trajetórias sintéticas.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from barnes.geometry.holes import generate_holes
from barnes.io.trim import interval_from_seconds
from barnes.pose.series import (
    POSE_CSV_COLUMNS,
    SeriesError,
    build_series,
    head_angle_deg,
    px_to_cm,
    read_pose_csv,
)
from barnes.pose.trajectory import read_metadata, read_trajectory, write_trajectory

DIRECTIONS_DEG = [0, 45, 90, 135, 180, 225, 270, 315]


def _circular_error(a_deg, b_deg):
    diff = np.abs(np.asarray(a_deg) - np.asarray(b_deg)) % 360.0
    return np.minimum(diff, 360.0 - diff)


def _straight_crossing(direction_deg, *, frames=50, step_px=4.0, body_px=20.0):
    """Animal atravessando a plataforma em linha reta, cabeça na direção do movimento.

    Coordenadas de imagem (y para baixo), como as do vídeo: o ângulo segue a
    mesma fórmula de `holes.py` (x = cos, y = +sin).
    """
    rad = math.radians(direction_deg)
    unit = np.array([math.cos(rad), math.sin(rad)])
    start = np.array([320.0, 240.0]) - unit * step_px * frames / 2
    center = start + np.outer(np.arange(frames), unit) * step_px
    snout = center + unit * body_px
    return center, snout


# --- px → cm (SCRUM-117) -------------------------------------------------------


def test_px_to_cm_uses_the_injected_scale_on_both_axes():
    points = np.array([[100.0, 50.0], [0.0, 640.0]])
    assert px_to_cm(points, 0.25).tolist() == [[25.0, 12.5], [0.0, 160.0]]


def test_px_to_cm_keeps_missing_points_missing():
    converted = px_to_cm(np.array([10.0, np.nan]), 0.1)
    assert converted[0] == pytest.approx(1.0)
    assert np.isnan(converted[1])


def test_px_to_cm_matches_known_distance():
    # 10 cm de régua medidos como 50 px → 0,2 cm/px; 125 px = 25 cm.
    cm_per_px = 10 / 50
    assert px_to_cm(np.array([125.0]), cm_per_px)[0] == pytest.approx(25.0)


@pytest.mark.parametrize("scale", [0, -0.1, math.nan, math.inf, True])
def test_px_to_cm_rejects_invalid_scale(scale):
    with pytest.raises(ValueError, match="cm_per_px"):
        px_to_cm(np.array([1.0]), scale)


# --- θ pelo eixo centro → focinho (SCRUM-119) ----------------------------------


@pytest.mark.parametrize(
    ("dx", "dy", "expected"),
    [
        (1, 0, 0.0),  # direita da imagem
        (0, 1, 90.0),  # para baixo na tela = sentido horário a partir de +x
        (-1, 0, 180.0),
        (0, -1, 270.0),  # para cima na tela
        (1, 1, 45.0),
    ],
)
def test_theta_convention_zero_at_plus_x_clockwise_on_screen(dx, dy, expected):
    theta = head_angle_deg(np.array([10.0]), np.array([10.0]), np.array([10.0 + dx]),
                           np.array([10.0 + dy]))
    assert theta[0] == pytest.approx(expected)


def test_theta_matches_hole_angle_convention_of_geometry():
    # Focinho apontando do centro da plataforma para cada buraco → θ = holes.angle_deg.
    geometry = generate_holes(
        center_x_px=300, center_y_px=200, platform_radius_px=150, hole_count=12,
        start_angle_deg=10, target_hole_number=0, hole_radius_px=8,
    )
    for hole in geometry.holes:
        theta = head_angle_deg(
            np.array([geometry.center_x_px]), np.array([geometry.center_y_px]),
            np.array([hole.x_px]), np.array([hole.y_px]),
        )[0]
        assert _circular_error(theta, hole.angle_deg) < 1e-9


def test_theta_stays_in_zero_to_360():
    theta = head_angle_deg(np.zeros(3), np.zeros(3), np.array([1.0, 1.0, 1.0]),
                           np.array([-1e-300, 0.0, -1e-12]))
    assert ((theta >= 0) & (theta < 360)).all()


def test_theta_is_nan_when_a_point_is_missing_or_points_coincide():
    theta = head_angle_deg(
        np.array([0.0, 0.0, 5.0]), np.array([0.0, np.nan, 5.0]),
        np.array([np.nan, 1.0, 5.0]), np.array([1.0, 1.0, 5.0]),
    )
    assert np.isnan(theta).all()


# --- Cenário 2: θ concorda com a direção de deslocamento -----------------------


@pytest.mark.parametrize("direction_deg", DIRECTIONS_DEG)
def test_theta_follows_straight_crossing_without_noise(direction_deg):
    center, snout = _straight_crossing(direction_deg)
    theta = head_angle_deg(center[:, 0], center[:, 1], snout[:, 0], snout[:, 1])
    motion = np.degrees(np.arctan2(np.diff(center[:, 1]), np.diff(center[:, 0]))) % 360
    assert _circular_error(theta[1:], motion).max() < 1e-6
    assert _circular_error(theta, direction_deg).max() < 1e-6


@pytest.mark.parametrize("direction_deg", DIRECTIONS_DEG)
def test_theta_follows_straight_crossing_with_pixel_noise(direction_deg):
    # Tolerância documentada em docs/contrato-trajetoria.md: σ = 1 px, corpo de
    # 20 px → desvio mediano ≤ 5°. Tolerância do teste, não limiar do laboratório.
    rng = np.random.default_rng(direction_deg)
    center, snout = _straight_crossing(direction_deg, frames=200)
    center = center + rng.normal(0, 1.0, center.shape)
    snout = snout + rng.normal(0, 1.0, snout.shape)
    theta = head_angle_deg(center[:, 0], center[:, 1], snout[:, 0], snout[:, 1])
    assert np.median(_circular_error(theta, direction_deg)) <= 5.0


def test_theta_is_scale_invariant():
    center, snout = _straight_crossing(135)
    in_px = head_angle_deg(center[:, 0], center[:, 1], snout[:, 0], snout[:, 1])
    c, s = px_to_cm(center, 0.17), px_to_cm(snout, 0.17)
    in_cm = head_angle_deg(c[:, 0], c[:, 1], s[:, 0], s[:, 1])
    assert np.allclose(in_px, in_cm)


# --- build_series: ausência marcada (SCRUM-121) e aviso de fps (SCRUM-118) ------

FPS = 10.0
INTERVAL = interval_from_seconds(1.0, 1.4, FPS, manually_adjusted=True)  # quadros 10..14


def _write_pose_csv(path, rows):
    """Escreve um pose.csv no formato de `pose infer`; None = célula vazia (ausente)."""
    lines = [",".join(POSE_CSV_COLUMNS)]
    for frame, points in rows:
        cells = ["abc123", str(frame), str(frame / FPS)]
        for point in ("focinho", "centro_corpo", "base_cauda"):
            x, y, conf = points.get(point, (None, None, None))
            cells += ["" if v is None else str(v) for v in (x, y, conf)]
        lines.append(",".join(cells))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _moving_right(frame):
    """Animal andando para a direita: centro em x = 10·quadro, focinho 20 px à frente."""
    x = 10.0 * frame
    return {
        "focinho": (x + 20, 100.0, 0.9),
        "centro_corpo": (x, 100.0, 0.8),
        "base_cauda": (x - 20, 100.0, 0.7),
    }


def _series(pose, **overrides):
    kwargs = {
        "trial_id": 5,
        "execucao_id": 9,
        "expected_frames": (10, 14),
        "fps": FPS,
        "interval": INTERVAL,
        "fps_variable": False,
        "cm_per_px": 0.1,
        "content_hash": "f" * 64,
        "model_id": "sleap-maze-1-abc",
    } | overrides
    return build_series(pose, **kwargs)


def test_series_has_one_row_per_frame_in_cm_degrees_and_seconds(tmp_path):
    # Cenário 1 (parte calculada): uma linha por quadro, x/y em cm, θ em graus, t em s.
    pose = read_pose_csv(_write_pose_csv(tmp_path / "pose.csv",
                                         [(f, _moving_right(f)) for f in range(10, 15)]))
    table = _series(pose)
    assert table.column("quadro").to_pylist() == [10, 11, 12, 13, 14]
    assert table.column("t_s").to_pylist() == pytest.approx([0.0, 0.1, 0.2, 0.3, 0.4])
    assert table.column("centro_corpo_x_cm_image").to_pylist() == pytest.approx(
        [10.0, 11.0, 12.0, 13.0, 14.0]
    )
    assert table.column("focinho_y_cm_image").to_pylist() == pytest.approx([10.0] * 5)
    assert table.column("theta_deg_image").to_pylist() == pytest.approx([0.0] * 5)
    assert all(table.column("pose_valida").to_pylist())
    assert not any(table.column("interpolado").to_pylist())
    meta = read_metadata(table)
    assert (meta["cm_per_px"], meta["px_per_10cm"]) == (0.1, pytest.approx(100.0))


def test_missing_snout_keeps_the_row_marked_absent_without_repeating_previous(tmp_path):
    # Cenário 3: o modelo não detectou o focinho no quadro 12.
    rows = [(f, _moving_right(f)) for f in range(10, 15)]
    rows[2][1]["focinho"] = (None, None, None)
    table = _series(read_pose_csv(_write_pose_csv(tmp_path / "pose.csv", rows)))

    assert table.num_rows == 5  # a linha existe
    row = {name: table.column(name)[2].as_py() for name in table.column_names}
    assert row["quadro"] == 12
    assert math.isnan(row["focinho_x_cm_image"]) and math.isnan(row["focinho_y_cm_image"])
    assert math.isnan(row["focinho_confianca"])
    assert row["focinho_valido"] is False
    assert row["pose_valida"] is False
    assert math.isnan(row["theta_deg_image"])
    # O resto do quadro continua: centro e cauda detectados não são descartados.
    assert row["centro_corpo_valido"] is True
    assert row["centro_corpo_x_cm_image"] == pytest.approx(12.0)
    # Nada copiado do quadro 11.
    assert row["focinho_x_cm_image"] != table.column("focinho_x_cm_image")[1].as_py()


def test_half_detected_point_is_absent_on_both_axes(tmp_path):
    rows = [(f, _moving_right(f)) for f in range(10, 15)]
    rows[0][1]["base_cauda"] = (80.0, None, 0.3)  # só x: ponto inválido
    table = _series(read_pose_csv(_write_pose_csv(tmp_path / "pose.csv", rows)))
    assert math.isnan(table.column("base_cauda_x_cm_image")[0].as_py())
    assert table.column("base_cauda_valido")[0].as_py() is False
    assert table.column("pose_valida")[0].as_py() is True  # θ não depende da cauda


def test_missing_frame_in_pose_is_an_error_not_a_silent_gap(tmp_path):
    rows = [(f, _moving_right(f)) for f in (10, 11, 13, 14)]
    pose = read_pose_csv(_write_pose_csv(tmp_path / "pose.csv", rows))
    with pytest.raises(SeriesError, match=r"\[12\]"):
        _series(pose)


def test_variable_fps_warning_reaches_every_row_and_metadata(tmp_path):
    pose = read_pose_csv(_write_pose_csv(tmp_path / "pose.csv",
                                         [(f, _moving_right(f)) for f in range(10, 15)]))
    table = _series(pose, fps_variable=True)
    assert all(table.column("fps_variavel").to_pylist())
    assert read_metadata(table)["fps_variavel"] is True


def test_series_round_trips_through_the_contract(tmp_path):
    pose = read_pose_csv(_write_pose_csv(tmp_path / "pose.csv",
                                         [(f, _moving_right(f)) for f in range(10, 15)]))
    path = write_trajectory(_series(pose), tmp_path / "trial_5.parquet")
    assert read_trajectory(path).num_rows == 5


def test_pose_csv_with_other_header_is_rejected(tmp_path):
    path = tmp_path / "pose.csv"
    path.write_text("x_px,y_px,time_s\n1,2,0\n", encoding="utf-8")
    with pytest.raises(SeriesError, match="Cabeçalho"):
        read_pose_csv(path)


def test_invalid_scale_is_reported_as_series_error(tmp_path):
    pose = read_pose_csv(_write_pose_csv(tmp_path / "pose.csv",
                                         [(f, _moving_right(f)) for f in range(10, 15)]))
    with pytest.raises(SeriesError, match="cm_per_px"):
        _series(pose, cm_per_px=0)
