"""Teclado da janela de ajuste de `barnes maze create` (US-04), sem abrir janela.

`_apply_geometry_key` é a parte da janela interativa que não depende do
OpenCV: o laço de eventos só lê a tecla e chama esta função.
"""

from __future__ import annotations

import numpy as np
import pytest

from barnes import cli

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
    }


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
