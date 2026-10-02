"""Testes da CLI de trial e da rotação no `video load` (US-05).

As funções de banco são substituídas via monkeypatch — a persistência em si
é coberta pelos testes de integração de tests/db/. Assim estes testes rodam
sem Postgres.
"""

from __future__ import annotations

from contextlib import nullcontext

import numpy as np
import pytest
from typer.testing import CliRunner

from barnes import cli
from barnes.geometry.holes import generate_holes

runner = CliRunner()


@pytest.fixture
def fake_db(monkeypatch):
    """Banco falso: rotação e montagem de cada trial, mais o registro de chamadas."""
    state = {
        "rotations": {},
        "maze_config_ids": {},
        "geometry": generate_holes(
            center_x_px=320.0,
            center_y_px=240.0,
            platform_radius_px=200.0,
            hole_count=20,
            start_angle_deg=30.0,
            target_hole_number=3,
            hole_radius_px=10.0,
        ),
        "inserted": [],
        "set_rotation": [],
    }

    def get_trial_rotations(_conn, trial_ids):
        ids = list(trial_ids)
        unknown = [i for i in ids if i not in state["rotations"]]
        if unknown:
            raise ValueError(f"Trial(s) não encontrado(s): {unknown}.")
        return {i: state["rotations"][i] for i in ids}

    def set_trial_rotation(_conn, trial_id, rotation_deg):
        if trial_id not in state["rotations"]:
            raise ValueError(f"Trial {trial_id} não encontrado.")
        state["set_rotation"].append((trial_id, rotation_deg))

    def insert_trial(_conn, **kwargs):
        state["inserted"].append(kwargs)
        return 42

    monkeypatch.setattr(cli, "get_connection", lambda _dsn=None: nullcontext(object()))
    monkeypatch.setattr(cli, "get_trial_rotations", get_trial_rotations)
    monkeypatch.setattr(cli, "set_trial_rotation", set_trial_rotation)
    monkeypatch.setattr(
        cli, "get_trial_maze_config_id", lambda _conn, trial_id: state["maze_config_ids"][trial_id]
    )
    monkeypatch.setattr(cli, "get_maze_config", lambda _conn, _id: state["geometry"])
    monkeypatch.setattr(cli, "insert_trial", insert_trial)
    return state


def test_trial_show_prints_target_in_both_reference_frames(fake_db) -> None:
    fake_db["rotations"][1] = 0.0
    fake_db["maze_config_ids"][1] = 9

    result = runner.invoke(cli.app, ["trial", "show", "1"])

    assert result.exit_code == 0, result.output
    assert "montagem #9" in result.output
    assert "Alvo [plataforma] target_hole_platform: buraco #3" in result.output
    # 3 buracos x 18° a partir do buraco 0 de referência, independente do start_angle (30°).
    assert "Alvo [sala] target_angle_deg_room: 54.0°" in result.output


def test_trial_show_rotated_trial_keeps_room_position(fake_db) -> None:
    # Cenário 1: com rotação, muda o índice do alvo, não sua posição na sala.
    fake_db["rotations"][2] = 90.0
    fake_db["maze_config_ids"][2] = 9

    result = runner.invoke(cli.app, ["trial", "show", "2"])

    assert result.exit_code == 0, result.output
    assert "buraco #18" in result.output  # (3 - 5) mod 20
    assert "target_angle_deg_room: 54.0°" in result.output


def test_trial_show_refuses_trial_without_rotation(fake_db) -> None:
    # Cenário 3: recusa e identifica o trial, em vez de assumir 0°.
    fake_db["rotations"][7] = None
    fake_db["maze_config_ids"][7] = 9

    result = runner.invoke(cli.app, ["trial", "show", "7"])

    assert result.exit_code == 1
    assert "#7" in result.output
    assert "não registrada" in result.output


def test_trial_show_unknown_trial(fake_db) -> None:
    result = runner.invoke(cli.app, ["trial", "show", "99"])

    assert result.exit_code == 1
    assert "não encontrado" in result.output


def test_trial_set_rotation(fake_db) -> None:
    fake_db["rotations"][1] = None

    result = runner.invoke(cli.app, ["trial", "set-rotation", "1", "90"])

    assert result.exit_code == 0, result.output
    assert fake_db["set_rotation"] == [(1, 90.0)]
    assert "90°" in result.output


def test_trial_set_rotation_accepts_negative_after_double_dash(fake_db) -> None:
    fake_db["rotations"][1] = None

    result = runner.invoke(cli.app, ["trial", "set-rotation", "--", "1", "-90"])

    assert result.exit_code == 0, result.output
    assert fake_db["set_rotation"] == [(1, -90.0)]
    assert "270°" in result.output


def test_trial_set_rotation_unknown_trial(fake_db) -> None:
    result = runner.invoke(cli.app, ["trial", "set-rotation", "99", "0"])

    assert result.exit_code == 1
    assert "não encontrado" in result.output


def _load(make_mp4, *extra_args):
    return runner.invoke(
        cli.app,
        [
            "video",
            "load",
            str(make_mp4()),
            "--experiment-id",
            "1",
            "--maze-config-id",
            "1",
            "--no-preview",
            *extra_args,
        ],
    )


def test_video_load_records_zero_rotation_explicitly_by_default(fake_db, make_mp4) -> None:
    # B4/RN04: o LNBio não rotaciona; o 0° é gravado explicitamente, não por DEFAULT do banco.
    result = _load(make_mp4)

    assert result.exit_code == 0, result.output
    assert fake_db["inserted"][0]["rotation_deg"] == 0.0
    assert "rotação da plataforma: 0°" in result.output


def test_video_load_passes_informed_rotation(fake_db, make_mp4) -> None:
    result = _load(make_mp4, "--rotation-deg", "90")

    assert result.exit_code == 0, result.output
    assert fake_db["inserted"][0]["rotation_deg"] == 90.0


def test_maze_show_prints_image_and_room_angles(fake_db) -> None:
    result = runner.invoke(cli.app, ["maze", "show", "9"])

    assert result.exit_code == 0, result.output
    # start_angle 30°: o buraco 0 está a 30° na imagem e a 0° na sala.
    assert "#0: angulo [imagem]=30.0 [sala]=0.0" in result.output
    assert "(REF)" in result.output
    assert "#3: angulo [imagem]=84.0 [sala]=54.0" in result.output
    assert "(ALVO)" in result.output


def test_overlay_highlights_reference_hole(fake_db) -> None:
    geometry = fake_db["geometry"]
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    canvas = cli._draw_geometry_overlay(frame, geometry)

    def ring_pixel(hole):
        # Ponto no anel de destaque, logo além do raio do buraco (raio + 4 px).
        ring_radius = hole.radius_px + 4
        return tuple(canvas[round(hole.y_px), round(hole.x_px + ring_radius)])

    assert ring_pixel(geometry.holes[0]) == cli.REFERENCE_HOLE_COLOR
    assert ring_pixel(geometry.holes[1]) != cli.REFERENCE_HOLE_COLOR
