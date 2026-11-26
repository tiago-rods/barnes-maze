"""Integração de barnes.db.contingency (US-23) contra o Postgres de teste."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from barnes.db.connection import get_connection
from barnes.db.contingency import load_strategy_rows
from barnes.db.executions import record_processing_execution
from barnes.db.trial_results import insert_trial_result
from barnes.provenance import GitState, ThresholdsSnapshot

pytestmark = pytest.mark.skipif(
    not os.environ.get("BARNES_DATABASE_URL"),
    reason="Requer BARNES_TEST_DATABASE_URL apontando para um Postgres com o schema aplicado.",
)


@pytest.fixture
def conn():
    connection = get_connection()
    yield connection
    connection.rollback()
    connection.close()


@pytest.fixture
def experiment_and_maze(conn):
    with conn.cursor() as cur:
        user = cur.execute(
            "INSERT INTO users (email, name) VALUES (%s, 'Op') RETURNING id", (str(uuid4()),)
        ).fetchone()[0]
        experiment = cur.execute(
            "INSERT INTO experiments (user_id, name) VALUES (%s, 'Exp') RETURNING id", (user,)
        ).fetchone()[0]
        maze_config_id = cur.execute(
            """
            INSERT INTO maze_configs (experiment_id, name, arena_diameter_cm, hole_count, hole_diameter_cm)
            VALUES (%s, 'M', 90.0, 20, 5.0) RETURNING id
            """,
            (experiment,),
        ).fetchone()[0]
    return experiment, maze_config_id


def _trial(conn, experiment_id, maze_config_id, *, day_number, trial_number_in_day=1, phase="acquisition"):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trials (
                experiment_id, maze_config_id, filename, filepath, phase,
                day_number, trial_number_in_day, content_hash, width_px,
                height_px, fps_declared, fps_real, frame_count, duration_s
            )
            VALUES (%s, %s, 't.mp4', 't.mp4', %s, %s, %s, %s, 640, 480, 30, 30, 300, 10)
            RETURNING id
            """,
            (experiment_id, maze_config_id, phase, day_number, trial_number_in_day, str(uuid4())),
        )
        return cur.fetchone()[0]


def _classify(conn, trial_id, maze_config_id, *, search_strategy):
    execucao_id = record_processing_execution(
        conn,
        trial_id=trial_id,
        maze_config_id=maze_config_id,
        parameters={"origem": "teste"},
        thresholds=ThresholdsSnapshot(values={}, sha256="0" * 64, path="teste.yaml"),
        git=GitState(commit="a" * 40, dirty=False),
        video_hash="hash",
        started_at=datetime.now(UTC),
    )
    insert_trial_result(
        conn,
        trial_id,
        execucao_id=execucao_id,
        distance_cm=None,
        speed_mean_cm=None,
        route_efficiency=None,
        px_per_10cm_used=100.0,
        calculated_at=datetime.now(UTC),
        search_strategy=search_strategy,
    )


def test_load_strategy_rows_includes_unclassified_trials_as_none(conn, experiment_and_maze):
    experiment_id, maze_config_id = experiment_and_maze
    classified = _trial(conn, experiment_id, maze_config_id, day_number=1)
    _classify(conn, classified, maze_config_id, search_strategy="spatial")
    unclassified = _trial(conn, experiment_id, maze_config_id, day_number=1, trial_number_in_day=2)

    rows = load_strategy_rows(conn, experiment_id)

    by_trial = {row["trial_id"]: row for row in rows}
    assert by_trial[classified]["search_strategy"] == "spatial"
    assert by_trial[classified]["session"] == 1
    assert by_trial[unclassified]["search_strategy"] is None


def test_load_strategy_rows_reads_latest_result_per_trial(conn, experiment_and_maze):
    experiment_id, maze_config_id = experiment_and_maze
    trial_id = _trial(conn, experiment_id, maze_config_id, day_number=2)
    _classify(conn, trial_id, maze_config_id, search_strategy="random")
    _classify(conn, trial_id, maze_config_id, search_strategy="serial")

    rows = load_strategy_rows(conn, experiment_id)

    assert len(rows) == 1
    assert rows[0]["search_strategy"] == "serial"


def test_load_strategy_rows_filters_by_phase(conn, experiment_and_maze):
    experiment_id, maze_config_id = experiment_and_maze
    _trial(conn, experiment_id, maze_config_id, day_number=1, phase="acquisition")
    _trial(conn, experiment_id, maze_config_id, day_number=1, trial_number_in_day=2, phase="probe")

    rows = load_strategy_rows(conn, experiment_id, phase="probe")

    assert len(rows) == 1


def test_load_strategy_rows_reads_group_label(conn, experiment_and_maze):
    experiment_id, maze_config_id = experiment_and_maze
    _trial(conn, experiment_id, maze_config_id, day_number=1)
    with conn.cursor() as cur:
        cur.execute("UPDATE experiments SET group_label = 'WT' WHERE id = %s", (experiment_id,))

    rows = load_strategy_rows(conn, experiment_id)

    assert rows[0]["grupo"] == "WT"
