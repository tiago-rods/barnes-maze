"""Integridade do esquema da US-27 (migração 0007): nenhuma métrica ou evento sem execução.

Integração contra o Postgres de teste (BARNES_TEST_DATABASE_URL, ver
tests/conftest.py); pulados sem banco. Cada teste desfaz o que inseriu.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from barnes.db.connection import get_connection
from barnes.db.executions import get_execution, record_processing_execution
from barnes.db.hole_events import insert_hole_event, list_hole_events
from barnes.db.trial_results import insert_trial_result
from barnes.provenance import GitState, ThresholdsSnapshot

pytestmark = pytest.mark.skipif(
    not os.environ.get("BARNES_DATABASE_URL"),
    reason="Requer BARNES_TEST_DATABASE_URL apontando para um Postgres com o schema aplicado.",
)

THRESHOLDS = ThresholdsSnapshot(
    values={"encontrar": {"distancia_cm": None}}, sha256="b" * 64, path="configs/default.yaml"
)


@pytest.fixture
def conn():
    connection = get_connection()
    yield connection
    connection.rollback()
    connection.close()


@pytest.fixture
def setup(conn):
    """Experimento com animal, montagem com um buraco e dois trials do mesmo dia."""
    with conn.cursor() as cur:
        user = cur.execute(
            "INSERT INTO users (email, name) VALUES (%s, 'Op') RETURNING id", (str(uuid4()),)
        ).fetchone()[0]
        experiment = cur.execute(
            "INSERT INTO experiments (user_id, name) VALUES (%s, 'Exp') RETURNING id", (user,)
        ).fetchone()[0]
        cur.execute("INSERT INTO subjects (experiment_id, name) VALUES (%s, 'Rato 7')", (experiment,))
        maze = cur.execute(
            """
            INSERT INTO maze_configs (experiment_id, name, arena_diameter_cm, hole_count,
                                      hole_diameter_cm)
            VALUES (%s, 'M', 120, 20, 5) RETURNING id
            """,
            (experiment,),
        ).fetchone()[0]
        hole = cur.execute(
            "INSERT INTO holes (maze_config_id, hole_number, angle_deg) VALUES (%s, 0, 0) "
            "RETURNING id",
            (maze,),
        ).fetchone()[0]
        trials = [
            cur.execute(
                """
                INSERT INTO trials (experiment_id, maze_config_id, filename, filepath, phase,
                    day_number, trial_number_in_day, content_hash, width_px, height_px,
                    fps_declared, fps_real, frame_count, duration_s)
                VALUES (%s, %s, 'v.mp4', 'v.mp4', 'acquisition', 3, %s, %s, 640, 480,
                        25, 25, 100, 4)
                RETURNING id
                """,
                (experiment, maze, number, str(uuid4())),
            ).fetchone()[0]
            for number in (1, 2)
        ]
    return {"experiment": experiment, "maze": maze, "hole": hole, "trials": trials}


CLEAN = GitState("c" * 40, False)


def _execution(conn, trial, maze, *, git=CLEAN):
    return record_processing_execution(
        conn,
        trial_id=trial,
        maze_config_id=maze,
        parameters={"trajectory": "t.csv"},
        thresholds=THRESHOLDS,
        git=git,
        video_hash="hash",
        started_at=datetime.now(UTC),
    )


def _raw_metric(conn, trial, execucao_id):
    conn.execute(
        "INSERT INTO trial_results (trial_id, execucao_id, distance_cm) VALUES (%s, %s, 1.0)",
        (trial, execucao_id),
    )


# --- SCRUM-158: métrica órfã é erro de esquema ---------------------------------


def test_metric_without_execution_is_rejected(conn, setup):
    with pytest.raises(psycopg.errors.NotNullViolation):
        _raw_metric(conn, setup["trials"][0], None)


def test_metric_pointing_to_missing_execution_is_rejected(conn, setup):
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _raw_metric(conn, setup["trials"][0], 2_000_000_000)


def test_metric_cannot_borrow_execution_of_another_trial(conn, setup):
    first, second = setup["trials"]
    other = _execution(conn, second, setup["maze"])
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _raw_metric(conn, first, other)


def test_one_metric_row_per_execution(conn, setup):
    trial = setup["trials"][0]
    execucao_id = _execution(conn, trial, setup["maze"])
    _raw_metric(conn, trial, execucao_id)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _raw_metric(conn, trial, execucao_id)


def test_hole_event_without_execution_is_rejected(conn, setup):
    with pytest.raises(psycopg.errors.NotNullViolation):
        conn.execute(
            "INSERT INTO evento_buraco (trial_id, hole_id, tipo, quadro, t_s) "
            "VALUES (%s, %s, 'descoberta', 10, 0.4)",
            (setup["trials"][0], setup["hole"]),
        )


# --- execucao: proveniência registrada e consultável (Cenários 1, 2 e 4) -------


def test_processing_execution_records_provenance(conn, setup):
    trial = setup["trials"][0]
    execucao_id = _execution(conn, trial, setup["maze"])
    insert_trial_result(
        conn, trial, execucao_id=execucao_id, distance_cm=1.0, speed_mean_cm=1.0,
        route_efficiency=None, px_per_10cm_used=50.0, calculated_at=datetime.now(UTC),
    )

    stored = get_execution(conn, execucao_id)
    assert stored.kind == "processamento"
    assert stored.model_id is None
    assert stored.git_commit == "c" * 40
    assert stored.limiares == THRESHOLDS.values
    assert stored.limiares_sha256 == THRESHOLDS.sha256
    assert stored.parametros == {"trajectory": "t.csv"}
    assert stored.recorded_at is not None
    assert stored.reproducible


def test_dirty_execution_is_not_reproducible(conn, setup):
    execucao_id = _execution(conn, setup["trials"][0], setup["maze"], git=GitState("c" * 40, True))
    stored = get_execution(conn, execucao_id)
    assert stored.git_dirty is True
    assert not stored.reproducible


def test_unknown_git_state_is_not_reproducible(conn, setup):
    execucao_id = _execution(conn, setup["trials"][0], setup["maze"], git=GitState(None, None))
    assert not get_execution(conn, execucao_id).reproducible


def test_processing_without_thresholds_is_rejected(conn, setup):
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO execucao (kind, maze_config_id, trial_id, status, metadata) "
            "VALUES ('processamento', %s, %s, 'concluido', %s)",
            (setup["maze"], setup["trials"][0], Jsonb({})),
        )


def test_pose_execution_still_requires_model(conn, setup):
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO execucao (kind, maze_config_id, status, metadata) "
            "VALUES ('treino', %s, 'concluido', %s)",
            (setup["maze"], Jsonb({})),
        )


def test_execution_stays_immutable(conn, setup):
    execucao_id = _execution(conn, setup["trials"][0], setup["maze"])
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        conn.execute("UPDATE execucao SET git_dirty = FALSE WHERE id = %s", (execucao_id,))


# --- evento_buraco e sessao ----------------------------------------------------


def test_hole_events_round_trip_ordered_by_time(conn, setup):
    trial = setup["trials"][0]
    execucao_id = _execution(conn, trial, setup["maze"])
    for quadro, t_s, tipo in ((50, 2.0, "entrada"), (10, 0.4, "descoberta")):
        insert_hole_event(
            conn, trial_id=trial, hole_id=setup["hole"], execucao_id=execucao_id,
            tipo=tipo, quadro=quadro, t_s=t_s,
        )
    events = list_hole_events(conn, trial_id=trial)
    assert [(e.tipo, e.quadro) for e in events] == [("descoberta", 10), ("entrada", 50)]
    assert {e.execucao_id for e in events} == {execucao_id}


def test_session_view_groups_trials_by_animal_and_day(conn, setup):
    row = conn.execute(
        "SELECT animal, numero_sessao, tipo, trials FROM sessao WHERE experiment_id = %s",
        (setup["experiment"],),
    ).fetchone()
    assert row == ("Rato 7", 3, "acquisition", 2)


def test_pose_coverage_requires_its_execution(conn, setup):
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "UPDATE trials SET cobertura_pose = 0.99 WHERE id = %s", (setup["trials"][0],)
        )
