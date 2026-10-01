"""Testes de integração de src/barnes/db/trials.py.

Exigem um Postgres com o schema de database/migrations/ aplicado, apontado
por BARNES_DATABASE_URL. São pulados automaticamente se a variável não
estiver definida (ex.: rodando `pytest` sem banco configurado).
"""

from __future__ import annotations

import os

import pytest

from barnes.db.connection import get_connection
from barnes.db.trials import insert_trial
from barnes.io.trim import build_trial_interval
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


def test_insert_trial_persists_interval(conn, experiment_and_maze_config, make_mp4) -> None:
    """US-03 RN04 — o intervalo útil resolvido fica gravado no registro do trial."""
    experiment_id, maze_config_id = experiment_and_maze_config
    video = load_trial_video(make_mp4(frame_count=10, fps=10.0))
    interval = build_trial_interval(video, start_s=0.2, end_s=0.8)

    trial_id = insert_trial(
        conn,
        experiment_id=experiment_id,
        maze_config_id=maze_config_id,
        video=video,
        phase="acquisition",
        day_number=1,
        trial_number_in_day=1,
        interval=interval,
    )

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT start_time_seconds, end_time_seconds, interval_manually_adjusted
            FROM trials WHERE id = %s
            """,
            (trial_id,),
        )
        row = cur.fetchone()

    assert row == (0.2, 0.8, True)


def test_insert_trial_without_interval_defaults_to_not_manually_adjusted(
    conn, experiment_and_maze_config, make_mp4
) -> None:
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
    )

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT start_time_seconds, end_time_seconds, interval_manually_adjusted
            FROM trials WHERE id = %s
            """,
            (trial_id,),
        )
        row = cur.fetchone()

    assert row == (None, None, False)


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
        )
