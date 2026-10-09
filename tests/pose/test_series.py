"""Conversão px→cm e orientação da cabeça θ (US-09, SCRUM-117/119/122, Cenário 2).

Sem banco nem GPU: escala fixa injetada e trajetórias sintéticas.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from barnes.geometry.holes import generate_holes
from barnes.pose.series import head_angle_deg, px_to_cm

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
