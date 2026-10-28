"""Testes de integração de src/barnes/db/maze_configs.py.

Exigem um Postgres com o schema de database/migrations/ aplicado, apontado
por BARNES_DATABASE_URL. São pulados automaticamente se a variável não
estiver definida (ex.: rodando `pytest` sem banco configurado).
"""

from __future__ import annotations

import os

import pytest

from barnes.db.connection import get_connection
from barnes.db.maze_configs import get_hole_ids, get_maze_config, insert_maze_config
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

    # Desde a migração 0005 todas as coordenadas em pixel são DOUBLE PRECISION:
    # o round-trip é exato, sem o arredondamento ao pixel que a 0001 fazia
    # (x_px/y_px dos buracos saem de cos/sin e têm parte fracionária).
    assert loaded.center_x_px == pytest.approx(geometry.center_x_px)
    assert loaded.center_y_px == pytest.approx(geometry.center_y_px)
    assert loaded.platform_radius_px == pytest.approx(geometry.platform_radius_px)
    assert loaded.hole_count == geometry.hole_count
    for expected, actual in zip(geometry.holes, loaded.holes):
        assert actual.hole_number == expected.hole_number
        assert actual.angle_deg == pytest.approx(expected.angle_deg)
        assert actual.x_px == pytest.approx(expected.x_px)
        assert actual.y_px == pytest.approx(expected.y_px)
        assert actual.radius_px == pytest.approx(expected.radius_px)
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


def test_get_hole_ids_maps_hole_number_to_primary_key(conn, experiment_id) -> None:
    geometry = _sample_geometry()
    maze_config_id = insert_maze_config(
        conn,
        experiment_id=experiment_id,
        name="config de teste",
        arena_diameter_cm=90.0,
        hole_diameter_cm=5.0,
        geometry=geometry,
    )

    hole_ids = get_hole_ids(conn, maze_config_id)

    assert set(hole_ids) == {hole.hole_number for hole in geometry.holes}
    with conn.cursor() as cur:
        for hole_number, hole_id in hole_ids.items():
            cur.execute(
                "SELECT maze_config_id, hole_number FROM holes WHERE id = %s", (hole_id,)
            )
            assert cur.fetchone() == (maze_config_id, hole_number)


def test_get_hole_ids_empty_for_maze_without_holes(conn, experiment_id) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO maze_configs (experiment_id, name, arena_diameter_cm, hole_count,
                                      hole_diameter_cm)
            VALUES (%s, 'sem buracos', 90.0, 20, 5.0) RETURNING id
            """,
            (experiment_id,),
        )
        maze_config_id = cur.fetchone()[0]

    assert get_hole_ids(conn, maze_config_id) == {}
