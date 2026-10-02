"""Teclado da janela de ajuste de `barnes maze create` (US-04), sem abrir janela.

`_apply_geometry_key` é a parte da janela interativa que não depende do
OpenCV: o laço de eventos só lê a tecla e chama esta função.
"""

from __future__ import annotations

import math

import cv2
import numpy as np
import pytest

from barnes import cli
from barnes.geometry.holes import generate_holes

FRAME = np.zeros((480, 640, 3), dtype=np.uint8)


@pytest.fixture
def state() -> dict:
    return {
        "center": (320.0, 240.0),
        "radius": 200.0,
        "start_angle": 0.0,
        "hole_count": 20,
        "target": 19,
        "hole_radius": 8.0,
        "dragging": False,
        "expected_hole_area_fraction": (8.0 / 200.0) ** 2,
    }


def _draw_platform_with_holes(
    *, center=(250.0, 250.0), platform_radius=200.0, ring_radius=150.0, hole_radius=10.0, count=12
) -> np.ndarray:
    """Disco claro com buracos escuros num anel, para testar a detecção sem GUI."""
    frame = np.full((500, 500, 3), 40, dtype=np.uint8)
    cv2.circle(frame, (int(center[0]), int(center[1])), int(platform_radius), (220, 220, 220), -1)
    for i in range(count):
        angle = 2 * math.pi * i / count
        hx = center[0] + ring_radius * math.cos(angle)
        hy = center[1] + ring_radius * math.sin(angle)
        cv2.circle(frame, (int(hx), int(hy)), int(hole_radius), (40, 40, 40), -1)
    return frame


def test_brackets_adjust_hole_radius_in_half_pixels(state) -> None:
    cli._apply_geometry_key(state, ord("]"), FRAME)
    cli._apply_geometry_key(state, ord("]"), FRAME)
    assert state["hole_radius"] == pytest.approx(9.0)
    cli._apply_geometry_key(state, ord("["), FRAME)
    assert state["hole_radius"] == pytest.approx(8.5)


def test_hole_radius_never_goes_below_minimum(state) -> None:
    state["hole_radius"] = 1.2
    for _ in range(5):
        cli._apply_geometry_key(state, ord("["), FRAME)
    assert state["hole_radius"] == pytest.approx(cli.MIN_HOLE_RADIUS_PX)


def test_adjusted_radius_reaches_the_generated_holes(state) -> None:
    state["hole_radius"] = 8.5
    geometry = cli._try_generate_geometry(state)
    assert {hole.radius_px for hole in geometry.holes} == {8.5}


def test_reducing_n_keeps_target_inside_range(state) -> None:
    cli._apply_geometry_key(state, ord("-"), FRAME)
    assert (state["hole_count"], state["target"]) == (19, 18)


def test_n_is_clamped_to_interactive_limits(state) -> None:
    state["hole_count"] = cli.MAX_INTERACTIVE_HOLE_COUNT
    cli._apply_geometry_key(state, ord("+"), FRAME)
    assert state["hole_count"] == cli.MAX_INTERACTIVE_HOLE_COUNT
    state["hole_count"] = 3
    cli._apply_geometry_key(state, ord("-"), FRAME)
    assert state["hole_count"] == 3


@pytest.mark.parametrize("key", [13, ord("q"), 27])
def test_confirm_keys_close_the_window(state, key) -> None:
    assert cli._apply_geometry_key(state, key, FRAME) is True


def test_other_keys_keep_the_window_open(state) -> None:
    assert cli._apply_geometry_key(state, ord("]"), FRAME) is False


def test_detect_holes_ring_fits_circle_through_the_holes_not_the_platform_edge() -> None:
    frame = _draw_platform_with_holes(
        center=(250.0, 250.0), platform_radius=200.0, ring_radius=150.0, hole_radius=10.0, count=12
    )
    detected = cli._detect_holes_ring(frame, expected_hole_area_fraction=(10.0 / 200.0) ** 2)
    assert detected is not None
    center_x, center_y, radius = detected
    assert center_x == pytest.approx(250.0, abs=2.0)
    assert center_y == pytest.approx(250.0, abs=2.0)
    assert radius == pytest.approx(150.0, abs=2.0)


def test_detect_holes_ring_requires_at_least_three_holes() -> None:
    frame = _draw_platform_with_holes(count=2)
    detected = cli._detect_holes_ring(frame, expected_hole_area_fraction=(10.0 / 200.0) ** 2)
    assert detected is None


def test_h_key_repositions_center_and_radius_to_the_holes_ring(state) -> None:
    frame = _draw_platform_with_holes(
        center=(250.0, 250.0), platform_radius=200.0, ring_radius=150.0, hole_radius=10.0, count=12
    )
    state["expected_hole_area_fraction"] = (10.0 / 200.0) ** 2
    cli._apply_geometry_key(state, ord("h"), frame)
    center_x, center_y = state["center"]
    assert center_x == pytest.approx(250.0, abs=2.0)
    assert center_y == pytest.approx(250.0, abs=2.0)
    assert state["radius"] == pytest.approx(150.0, abs=2.0)


def test_h_key_keeps_previous_geometry_when_too_few_holes_are_found(state) -> None:
    frame = _draw_platform_with_holes(count=2)
    cli._apply_geometry_key(state, ord("h"), frame)
    assert state["center"] == (320.0, 240.0)
    assert state["radius"] == 200.0


@pytest.fixture
def octagon() -> object:
    return generate_holes(
        center_x_px=250.0,
        center_y_px=250.0,
        platform_radius_px=150.0,
        hole_count=8,
        start_angle_deg=0.0,
        target_hole_number=0,
        hole_radius_px=10.0,
    )


def test_snap_moves_holes_with_a_nearby_candidate_and_recomputes_angle(octagon) -> None:
    # Buracos 0..5 têm um candidato "real" a 15 px de distância; 6 e 7, nenhum.
    offset_candidates = [
        (hole.x_px + 9.0, hole.y_px + 12.0) for hole in octagon.holes[:6]
    ]
    snapped, count = cli._snap_holes_to_detected_centers(
        octagon, offset_candidates, max_offset_px=20.0
    )
    assert count == 6
    for original, corrected in zip(octagon.holes[:6], snapped.holes[:6], strict=True):
        assert corrected.x_px == pytest.approx(original.x_px + 9.0)
        assert corrected.y_px == pytest.approx(original.y_px + 12.0)
        expected_angle = math.degrees(
            math.atan2(
                corrected.y_px - snapped.center_y_px, corrected.x_px - snapped.center_x_px
            )
        ) % 360.0
        assert corrected.angle_deg == pytest.approx(expected_angle)
    # Sem candidato por perto, 6 e 7 ficam exatamente como `generate_holes` os colocou.
    for original, corrected in zip(octagon.holes[6:], snapped.holes[6:], strict=True):
        assert corrected == original


def test_snap_ignores_candidates_beyond_max_offset(octagon) -> None:
    far_away = [(octagon.holes[0].x_px + 500.0, octagon.holes[0].y_px + 500.0)]
    snapped, count = cli._snap_holes_to_detected_centers(octagon, far_away, max_offset_px=20.0)
    assert count == 0
    assert snapped.holes == octagon.holes


def test_snap_assigns_each_candidate_to_only_the_nearest_hole(octagon) -> None:
    hole0, hole1 = octagon.holes[0], octagon.holes[1]
    # Um único candidato, mais perto do buraco 0 que do buraco 1, mas dentro
    # da tolerância dos dois: não pode "roubar" a correção do buraco 1.
    midpoint_closer_to_0 = (
        hole0.x_px + 0.4 * (hole1.x_px - hole0.x_px),
        hole0.y_px + 0.4 * (hole1.y_px - hole0.y_px),
    )
    tolerance = math.hypot(hole1.x_px - hole0.x_px, hole1.y_px - hole0.y_px)
    snapped, count = cli._snap_holes_to_detected_centers(
        octagon, [midpoint_closer_to_0], max_offset_px=tolerance
    )
    assert count == 1
    assert snapped.holes[0].x_px == pytest.approx(midpoint_closer_to_0[0])
    assert snapped.holes[0].y_px == pytest.approx(midpoint_closer_to_0[1])
    assert snapped.holes[1] == hole1
