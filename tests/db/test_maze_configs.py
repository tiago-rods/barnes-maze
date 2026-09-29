"""Testes de integração de src/barnes/db/maze_configs.py.

Exigem um Postgres com o schema de database/migrations/ aplicado, apontado
por BARNES_DATABASE_URL. São pulados automaticamente se a variável não
estiver definida (ex.: rodando `pytest` sem banco configurado).
"""

from __future__ import annotations

import os

import pytest

from barnes.db.connection import get_connection
from barnes.db.maze_configs import get_maze_config, insert_maze_config
from barnes.geometry.holes import generate_holes

pytestmark = pytest.mark.skipif(
    not os.environ.get("BARNES_DATABASE_URL"),
    reason="Requer BARNES_DATABASE_URL apontando para um Postgres com o schema aplicado.",
)


@pytest.fixture
def conn():
    connection = get_connection()
    yield connection
    connection.rollback()
    connection.close()


@pytest.fixture
def experiment_id(conn):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (email, name) VALUES (%s, %s) RETURNING id",
            ("teste@example.com", "Operador de teste"),
        )
        user_id = cur.fetchone()[0]

        cur.execute(
            "INSERT INTO experiments (user_id, name) VALUES (%s, %s) RETURNING id",
            (user_id, "Experimento de teste"),
        )
        return cur.fetchone()[0]


def _sample_geometry():
    return generate_holes(
        center_x_px=320.0,
        center_y_px=240.0,
        platform_radius_px=200.0,
        hole_count=20,
        start_angle_deg=0.0,
        target_hole_number=5,
        hole_radius_px=15.0,
    )


def test_insert_and_get_maze_config_roundtrip(conn, experiment_id) -> None:
    geometry = _sample_geometry()
    maze_config_id = insert_maze_config(
        conn,
        experiment_id=experiment_id,
        name="config de teste",
        arena_diameter_cm=90.0,
        hole_diameter_cm=5.0,
        geometry=geometry,
    )

    loaded = get_maze_config(conn, maze_config_id)

    # center_x_px/center_y_px (maze_configs) e x_px/y_px/radius_px (holes) são
    # INTEGER no schema (0001_create_schema.sql) — o round-trip arredonda para
    # o pixel mais próximo. angle_deg e platform_radius_px são DOUBLE
    # PRECISION e voltam com precisão total.
    assert loaded.center_x_px == pytest.approx(geometry.center_x_px, abs=1)
    assert loaded.center_y_px == pytest.approx(geometry.center_y_px, abs=1)
    assert loaded.platform_radius_px == pytest.approx(geometry.platform_radius_px)
    assert loaded.hole_count == geometry.hole_count
    for expected, actual in zip(geometry.holes, loaded.holes):
        assert actual.hole_number == expected.hole_number
        assert actual.angle_deg == pytest.approx(expected.angle_deg)
        assert actual.x_px == pytest.approx(expected.x_px, abs=1)
        assert actual.y_px == pytest.approx(expected.y_px, abs=1)
        assert actual.radius_px == pytest.approx(expected.radius_px, abs=1)
        assert actual.is_target == expected.is_target


def test_get_maze_config_reapplies_target_hole(conn, experiment_id) -> None:
    geometry = _sample_geometry()
    maze_config_id = insert_maze_config(
        conn,
        experiment_id=experiment_id,
        name="config de teste",
        arena_diameter_cm=90.0,
        hole_diameter_cm=5.0,
        geometry=geometry,
    )

    loaded = get_maze_config(conn, maze_config_id)

    assert loaded.target_hole.hole_number == geometry.target_hole.hole_number


def test_get_maze_config_missing_raises(conn) -> None:
    with pytest.raises(ValueError):
        get_maze_config(conn, 999999)
