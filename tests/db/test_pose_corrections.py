"""Correções manuais e qualidade de pose no banco (US-10, migração 0008).

Integração contra o Postgres de teste (BARNES_TEST_DATABASE_URL, ver
tests/conftest.py); pulados sem banco. Cada teste desfaz o que inseriu.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest

from barnes.db.connection import get_connection
from barnes.db.executions import record_processing_execution
from barnes.db.pose_corrections import (
    REVIEW_COMMAND,
    insert_pose_corrections,
    list_pose_corrections,
    list_reviewed_ranges,
)
from barnes.db.trials import set_pose_coverage
from barnes.pose.quality import PointCorrection
from barnes.provenance import GitState, ThresholdsSnapshot

pytestmark = pytest.mark.skipif(
    not os.environ.get("BARNES_DATABASE_URL"),
    reason="Requer BARNES_TEST_DATABASE_URL apontando para um Postgres com o schema aplicado.",
)

THRESHOLDS = ThresholdsSnapshot(
    values={"pose": {"cobertura_minima": 0.98}}, sha256="b" * 64, path="configs/default.yaml"
)


@pytest.fixture
def conn():
    connection = get_connection()
    yield connection
    connection.rollback()
    connection.close()


@pytest.fixture
def trials(conn):
    """Dois trials da mesma montagem."""
    with conn.cursor() as cur:
        user = cur.execute(
            "INSERT INTO users (email, name) VALUES (%s, 'Op') RETURNING id", (str(uuid4()),)
        ).fetchone()[0]
        experiment = cur.execute(
            "INSERT INTO experiments (user_id, name) VALUES (%s, 'Exp') RETURNING id", (user,)
        ).fetchone()[0]
        maze = cur.execute(
            """
            INSERT INTO maze_configs (experiment_id, name, arena_diameter_cm, hole_count,
                                      hole_diameter_cm)
            VALUES (%s, 'M', 120, 20, 5) RETURNING id
            """,
            (experiment,),
        ).fetchone()[0]
        ids = [
            cur.execute(
                """
                INSERT INTO trials (experiment_id, maze_config_id, filename, filepath, phase,
                    day_number, trial_number_in_day, content_hash, width_px, height_px,
                    fps_declared, fps_real, frame_count, duration_s)
                VALUES (%s, %s, 'v.mp4', 'v.mp4', 'acquisition', 1, %s, %s, 640, 480,
                        25, 25, 100, 4)
                RETURNING id
                """,
                (experiment, maze, number, str(uuid4())),
            ).fetchone()[0]
            for number in (1, 2)
        ]
    return {"maze": maze, "ids": ids}


def _execution(conn, trial, maze, *, parameters=None, report=None):
    return record_processing_execution(
        conn,
        trial_id=trial,
        maze_config_id=maze,
        parameters=parameters or {"comando": "pose series"},
        thresholds=THRESHOLDS,
        git=GitState("c" * 40, False),
        video_hash="hash",
        started_at=datetime.now(UTC),
        metadata=None if report is None else {"qualidade_pose": report},
    )


SNOUT_10 = PointCorrection(10, "focinho", 12.5, 30.0)


# --- correcao_pose: toda correção pertence a uma execução do mesmo trial (RN05) ---


def test_corrections_round_trip_in_registration_order(conn, trials):
    trial, maze = trials["ids"][0], trials["maze"]
    first = _execution(conn, trial, maze, parameters={"comando": REVIEW_COMMAND})
    second = _execution(conn, trial, maze, parameters={"comando": REVIEW_COMMAND})
    insert_pose_corrections(conn, trial_id=trial, execucao_id=second, corrections=[
        PointCorrection(10, "focinho", 99.0, 98.0)
    ])
    count = insert_pose_corrections(conn, trial_id=trial, execucao_id=first, corrections=[
        SNOUT_10, PointCorrection(11, "base_cauda", 1.0, 2.0)
    ])
    assert count == 2

    stored = list_pose_corrections(conn, trial)
    assert [(c.execucao_id, c.quadro, c.ponto) for c in stored] == [
        (first, 10, "focinho"), (first, 11, "base_cauda"), (second, 10, "focinho")
    ]
    assert stored[0].correction == SNOUT_10
    assert list_pose_corrections(conn, trials["ids"][1]) == []


def test_correction_cannot_borrow_execution_of_another_trial(conn, trials):
    first, second = trials["ids"]
    other = _execution(conn, second, trials["maze"])
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        insert_pose_corrections(conn, trial_id=first, execucao_id=other, corrections=[SNOUT_10])


def test_same_point_twice_in_one_session_is_rejected(conn, trials):
    trial = trials["ids"][0]
    execucao_id = _execution(conn, trial, trials["maze"])
    with pytest.raises(psycopg.errors.UniqueViolation):
        insert_pose_corrections(
            conn, trial_id=trial, execucao_id=execucao_id, corrections=[SNOUT_10, SNOUT_10]
        )


@pytest.mark.parametrize(
    ("ponto", "x_px"), [("orelha", 1.0), ("focinho", float("nan")), ("focinho", -1.0)]
)
def test_invalid_point_or_position_is_rejected_by_the_schema(conn, trials, ponto, x_px):
    trial = trials["ids"][0]
    execucao_id = _execution(conn, trial, trials["maze"])
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO correcao_pose (trial_id, execucao_id, quadro, ponto, x_px, y_px) "
            "VALUES (%s, %s, 1, %s, %s, 1.0)",
            (trial, execucao_id, ponto, x_px),
        )


def test_corrections_are_immutable(conn, trials):
    trial = trials["ids"][0]
    execucao_id = _execution(conn, trial, trials["maze"])
    insert_pose_corrections(conn, trial_id=trial, execucao_id=execucao_id, corrections=[SNOUT_10])
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        conn.execute("UPDATE correcao_pose SET x_px = 0 WHERE trial_id = %s", (trial,))


def test_reviewed_ranges_come_only_from_review_executions(conn, trials):
    trial, maze = trials["ids"][0], trials["maze"]
    _execution(conn, trial, maze, parameters={
        "comando": REVIEW_COMMAND, "trechos_revisados": [{"inicio": 10, "fim": 20}]
    })
    _execution(conn, trial, maze, parameters={
        "comando": "pose series", "trechos_revisados": [{"inicio": 50, "fim": 60}]
    })
    _execution(conn, trial, maze, parameters={"comando": REVIEW_COMMAND})  # sem trechos
    _execution(conn, trial, maze, parameters={
        "comando": REVIEW_COMMAND,
        "trechos_revisados": [{"inicio": 30, "fim": 31}, {"inicio": 40, "fim": 45}],
    })
    assert list_reviewed_ranges(conn, trial) == [(10, 20), (30, 31), (40, 45)]
    assert list_reviewed_ranges(conn, trials["ids"][1]) == []


# --- cobertura e VIEW qualidade_pose (RN03/RN06) -----------------------------------


@pytest.mark.parametrize(
    ("cobertura", "pendentes", "expected"),
    [
        (0.99, 0, "suficiente"),
        (0.98, 0, "suficiente"),
        (0.93, 0, "insuficiente"),
        (0.93, 2, "revisao_pendente"),
    ],
)
def test_quality_view_derives_the_mark(conn, trials, cobertura, pendentes, expected):
    trial = trials["ids"][0]
    report = {"cobertura": cobertura, "cobertura_minima": 0.98, "trechos_pendentes": pendentes}
    execucao_id = _execution(conn, trial, trials["maze"], report=report)
    set_pose_coverage(conn, trial, cobertura=cobertura, execucao_id=execucao_id)
    row = conn.execute(
        "SELECT cobertura_pose, cobertura_minima, trechos_pendentes, qualidade "
        "FROM qualidade_pose WHERE trial_id = %s",
        (trial,),
    ).fetchone()
    assert row == (pytest.approx(cobertura), 0.98, pendentes, expected)


def test_quality_is_null_without_coverage_or_report(conn, trials):
    first, second = trials["ids"]
    without_report = _execution(conn, second, trials["maze"])
    set_pose_coverage(conn, second, cobertura=0.5, execucao_id=without_report)
    rows = dict(
        conn.execute(
            "SELECT trial_id, qualidade FROM qualidade_pose WHERE trial_id = ANY(%s)",
            ([first, second],),
        ).fetchall()
    )
    assert rows == {first: None, second: None}


def test_set_pose_coverage_validates_value_trial_and_execution(conn, trials):
    first, second = trials["ids"]
    execucao_id = _execution(conn, first, trials["maze"])
    with pytest.raises(ValueError, match="entre 0 e 1"):
        set_pose_coverage(conn, first, cobertura=1.2, execucao_id=execucao_id)
    with pytest.raises(ValueError, match="não encontrado"):
        set_pose_coverage(conn, 2_000_000_000, cobertura=0.5, execucao_id=execucao_id)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        set_pose_coverage(conn, second, cobertura=0.5, execucao_id=execucao_id)
