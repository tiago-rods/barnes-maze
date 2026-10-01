"""Testes de integração de src/barnes/db/trials.py.

Exigem um Postgres com o schema de database/migrations/ aplicado, apontado
por BARNES_DATABASE_URL. São pulados automaticamente se a variável não
estiver definida (ex.: rodando `pytest` sem banco configurado).
"""

from __future__ import annotations

import os

import psycopg
import pytest

from barnes.db.connection import get_connection
from barnes.db.trials import (
    get_trial_maze_config_id,
    get_trial_rotations,
    insert_trial,
    set_trial_rotation,
)
from barnes.io.video import load_trial_video

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
def experiment_and_maze_config(conn):
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
        experiment_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO maze_configs
                (experiment_id, name, arena_diameter_cm, hole_count, hole_diameter_cm)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (experiment_id, "config de teste", 90.0, 20, 5.0),
        )
        maze_config_id = cur.fetchone()[0]

    return experiment_id, maze_config_id


def test_insert_trial_persists_video_metadata(conn, experiment_and_maze_config, make_mp4) -> None:
    experiment_id, maze_config_id = experiment_and_maze_config
    video = load_trial_video(make_mp4(frame_count=10, fps=10.0))

    trial_id = insert_trial(
        conn,
        experiment_id=experiment_id,
        maze_config_id=maze_config_id,
        video=video,
        phase="acquisition",
        day_number=1,
        trial_number_in_day=1,
        rotation_deg=0.0,
    )

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT content_hash, width_px, height_px, frame_count, fps_is_variable
            FROM trials WHERE id = %s
            """,
            (trial_id,),
        )
        row = cur.fetchone()

    assert row == (video.content_hash, video.width, video.height, video.frame_count, video.fps_is_variable)


def test_insert_trial_rejects_duplicate_content_hash(conn, experiment_and_maze_config, make_mp4) -> None:
    experiment_id, maze_config_id = experiment_and_maze_config
    video = load_trial_video(make_mp4(frame_count=10, fps=10.0))

    insert_trial(
        conn,
        experiment_id=experiment_id,
        maze_config_id=maze_config_id,
        video=video,
        phase="acquisition",
        day_number=1,
        trial_number_in_day=1,
        rotation_deg=0.0,
    )

    with pytest.raises(Exception, match="content_hash"):
        insert_trial(
            conn,
            experiment_id=experiment_id,
            maze_config_id=maze_config_id,
            video=video,
            phase="acquisition",
            day_number=1,
            trial_number_in_day=2,
            rotation_deg=0.0,
        )


def _insert(conn, experiment_and_maze_config, make_mp4, *, name, rotation_deg, frame_count=10):
    experiment_id, maze_config_id = experiment_and_maze_config
    video = load_trial_video(make_mp4(name=name, frame_count=frame_count, fps=10.0))
    return insert_trial(
        conn,
        experiment_id=experiment_id,
        maze_config_id=maze_config_id,
        video=video,
        phase="acquisition",
        day_number=1,
        trial_number_in_day=1,
        rotation_deg=rotation_deg,
    )


def test_insert_trial_persists_rotation(conn, experiment_and_maze_config, make_mp4) -> None:
    trial_id = _insert(conn, experiment_and_maze_config, make_mp4, name="a.mp4", rotation_deg=90.0)
    assert get_trial_rotations(conn, [trial_id]) == {trial_id: 90.0}


def test_insert_trial_normalizes_rotation(conn, experiment_and_maze_config, make_mp4) -> None:
    trial_id = _insert(conn, experiment_and_maze_config, make_mp4, name="a.mp4", rotation_deg=-90.0)
    assert get_trial_rotations(conn, [trial_id]) == {trial_id: 270.0}


def test_insert_trial_without_rotation_stays_null(
    conn, experiment_and_maze_config, make_mp4
) -> None:
    # US-05 RN01: ausência de valor é NULL ("não registrada"), nunca 0° implícito.
    trial_id = _insert(conn, experiment_and_maze_config, make_mp4, name="a.mp4", rotation_deg=None)
    assert get_trial_rotations(conn, [trial_id]) == {trial_id: None}


def test_rotation_column_has_no_silent_default(conn, experiment_and_maze_config, make_mp4) -> None:
    # O schema não define DEFAULT para a coluna (migração 0002).
    trial_id = _insert(conn, experiment_and_maze_config, make_mp4, name="a.mp4", rotation_deg=None)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_default FROM information_schema.columns
            WHERE table_name = 'trials' AND column_name = 'rotation_deg'
            """
        )
        assert cur.fetchone() == (None,)
    assert get_trial_rotations(conn, [trial_id])[trial_id] is None


def test_set_trial_rotation_updates_existing_trial(
    conn, experiment_and_maze_config, make_mp4
) -> None:
    trial_id = _insert(conn, experiment_and_maze_config, make_mp4, name="a.mp4", rotation_deg=None)
    set_trial_rotation(conn, trial_id, 45.0)
    assert get_trial_rotations(conn, [trial_id]) == {trial_id: 45.0}


def test_set_trial_rotation_rejects_unknown_trial(conn) -> None:
    with pytest.raises(ValueError, match="não encontrado"):
        set_trial_rotation(conn, -1, 0.0)


def test_get_trial_rotations_mixes_registered_and_missing(
    conn, experiment_and_maze_config, make_mp4
) -> None:
    with_rotation = _insert(
        conn, experiment_and_maze_config, make_mp4, name="a.mp4", rotation_deg=0.0
    )
    without_rotation = _insert(
        conn, experiment_and_maze_config, make_mp4, name="b.mp4", rotation_deg=None, frame_count=11
    )
    assert get_trial_rotations(conn, [with_rotation, without_rotation]) == {
        with_rotation: 0.0,
        without_rotation: None,
    }


def test_get_trial_rotations_rejects_unknown_trial(conn) -> None:
    # Trial inexistente não pode ser confundido com trial sem rotação.
    with pytest.raises(ValueError, match="não encontrado"):
        get_trial_rotations(conn, [-1])


def test_rotation_check_rejects_360(conn, experiment_and_maze_config, make_mp4) -> None:
    # O CHECK do banco protege mesmo quem grava sem passar pela normalização.
    trial_id = _insert(conn, experiment_and_maze_config, make_mp4, name="a.mp4", rotation_deg=0.0)
    with pytest.raises(psycopg.errors.CheckViolation), conn.cursor() as cur:
        cur.execute("UPDATE trials SET rotation_deg = 360 WHERE id = %s", (trial_id,))


def test_get_trial_maze_config_id(conn, experiment_and_maze_config, make_mp4) -> None:
    _, maze_config_id = experiment_and_maze_config
    trial_id = _insert(conn, experiment_and_maze_config, make_mp4, name="a.mp4", rotation_deg=0.0)
    assert get_trial_maze_config_id(conn, trial_id) == maze_config_id


def test_get_trial_maze_config_id_rejects_unknown_trial(conn) -> None:
    with pytest.raises(ValueError, match="não encontrado"):
        get_trial_maze_config_id(conn, -1)
