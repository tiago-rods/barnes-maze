"""Detalhes de entrada US-13, compatibilidade US-11 e transação US-27.

Testes de integração só usam BARNES_TEST_DATABASE_URL, isolado em conftest.py;
sem banco de teste, a validação da API continua sendo executada.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from barnes.db.connection import get_connection
from barnes.db.executions import record_processing_execution
from barnes.db.hole_events import (
    HoleEvent,
    get_event_pose_quality,
    insert_hole_event,
    list_hole_events,
)
from barnes.provenance import GitState, ThresholdsSnapshot

ENTRY_DETAILS = {
    "confirmed_at_s": 2.24,
    "discovery_quadro": 10,
    "discovery_t_s": 0.4,
    "delta_latency": 1.6,
    "delta_distance_cm": 8.75,
    "total_latency": 2.0,
    "total_distance_cm": 12.5,
    "issues": [],
}


def _insert(conn, **overrides):
    values = {
        "trial_id": 1,
        "hole_id": 2,
        "execucao_id": 3,
        "tipo": "entrada",
        "quadro": 50,
        "t_s": 2.0,
    }
    values.update(overrides)
    return insert_hole_event(conn, **values)


@pytest.mark.parametrize("details", [None, {}, ENTRY_DETAILS])
def test_insert_preserves_json_and_leaves_transaction_to_caller(details):
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (42,)
    assert _insert(conn, details=details) == 42
    _, parameters = cursor.execute.call_args.args
    assert parameters[-1].obj == (details or {})
    conn.commit.assert_not_called()
    conn.rollback.assert_not_called()


@pytest.mark.parametrize(
    "details",
    [
        {"delta_latency": float("nan")},
        {"total_distance_cm": float("inf")},
        {"issues": [{"value": float("-inf")}]},
        {"confirmed_at_s": object()},
    ],
)
def test_invalid_json_is_rejected_before_database_access(details):
    conn = MagicMock()
    with pytest.raises(ValueError, match="JSON finitos"):
        _insert(conn, details=details)
    conn.cursor.assert_not_called()


@pytest.mark.parametrize("details", [[], "entrada", 1, False])
def test_details_requires_object(details):
    conn = MagicMock()
    with pytest.raises(TypeError, match="objeto JSON"):
        _insert(conn, details=details)
    conn.cursor.assert_not_called()


def test_orphan_entry_preserves_missing_values_and_issues():
    conn = MagicMock()
    details = dict(
        ENTRY_DETAILS,
        discovery_quadro=None,
        discovery_t_s=None,
        delta_latency=None,
        delta_distance_cm=None,
        issues=[{"kind": "entrada_sem_descoberta", "trial_id": 1, "hole_id": 2}],
    )
    _insert(conn, details=details)
    cursor = conn.cursor.return_value.__enter__.return_value
    assert cursor.execute.call_args.args[1][-1].obj == details


def test_previous_hole_event_constructor_remains_compatible_without_shared_default():
    first = HoleEvent(1, 2, 3, 4, "descoberta", 5, 0.2, None, None)
    second = HoleEvent(2, 2, 3, 4, "descoberta", 6, 0.24, None, None)
    assert first.details == second.details == {}
    assert first.details is not second.details


def test_listing_retrieves_details_and_filters_same_execution():
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = [(1, 2, 3, 4, "entrada", 50, 2.0, None, None, ENTRY_DETAILS)]
    events = list_hole_events(conn, trial_id=2, execucao_id=4)
    assert events[0].details == ENTRY_DETAILS
    sql, parameters = cursor.execute.call_args.args
    assert "ORDER BY t_s, id" in sql
    assert "AND execucao_id = %s" in sql
    assert parameters == [2, 4]
    conn.commit.assert_not_called()


@pytest.mark.parametrize(
    "row",
    [(0.8, 10, 0.9, 2, "revisao_pendente"), (None, None, None, None, None)],
)
def test_quality_is_read_from_view_including_unprocessed_trial(row):
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = row
    result = get_event_pose_quality(conn, trial_id=7)
    assert result == dict(
        zip(
            (
                "cobertura_pose",
                "cobertura_execucao_id",
                "cobertura_minima",
                "trechos_pendentes",
                "qualidade",
            ),
            row,
            strict=True,
        )
    )
    sql, parameters = cursor.execute.call_args.args
    assert "FROM qualidade_pose" in sql
    assert parameters == (7,)
    conn.commit.assert_not_called()


def test_quality_query_rejects_unknown_trial():
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchone.return_value = None
    with pytest.raises(ValueError, match="Trial 7 não encontrado"):
        get_event_pose_quality(conn, trial_id=7)


@pytest.fixture
def conn():
    connection = get_connection()
    yield connection
    connection.rollback()
    connection.close()


@pytest.fixture
def setup(conn):
    with conn.cursor() as cursor:
        user = cursor.execute(
            "INSERT INTO users (email, name) VALUES (%s, 'Op') RETURNING id",
            (str(uuid4()),),
        ).fetchone()[0]
        experiment = cursor.execute(
            "INSERT INTO experiments (user_id, name) VALUES (%s, 'US13') RETURNING id",
            (user,),
        ).fetchone()[0]
        maze = cursor.execute(
            """
            INSERT INTO maze_configs
                (experiment_id, name, arena_diameter_cm, hole_count, hole_diameter_cm)
            VALUES (%s, 'M', 120, 20, 5) RETURNING id
            """,
            (experiment,),
        ).fetchone()[0]
        hole = cursor.execute(
            "INSERT INTO holes (maze_config_id, hole_number, angle_deg) "
            "VALUES (%s, 0, 0) RETURNING id",
            (maze,),
        ).fetchone()[0]
        trials = [
            cursor.execute(
                """
                INSERT INTO trials (experiment_id, maze_config_id, filename, filepath, phase,
                    day_number, trial_number_in_day, content_hash, width_px, height_px,
                    fps_declared, fps_real, frame_count, duration_s)
                VALUES (%s, %s, 'v.mp4', 'v.mp4', 'acquisition', 1, %s, %s,
                    640, 480, 25, 25, 100, 4) RETURNING id
                """,
                (experiment, maze, number, str(uuid4())),
            ).fetchone()[0]
            for number in (1, 2)
        ]
    return {"maze": maze, "hole": hole, "trials": trials}


def _execution(conn, setup, trial_index=0):
    return record_processing_execution(
        conn,
        trial_id=setup["trials"][trial_index],
        maze_config_id=setup["maze"],
        parameters={"comando": "events entries"},
        thresholds=ThresholdsSnapshot(
            values={"entrada": {"duracao_minima_s": 0.24}},
            sha256="b" * 64,
            path="configs/test.yaml",
        ),
        git=GitState("c" * 40, False),
        video_hash="d" * 64,
        started_at=datetime.now(UTC),
    )


@pytest.mark.skipif(
    not os.environ.get("BARNES_DATABASE_URL"),
    reason="Requer BARNES_TEST_DATABASE_URL e migração 0009_us13_entry_details.sql aplicada.",
)
class TestPostgresHoleEventDetails:
    def test_unprocessed_trial_quality_remains_unavailable(self, conn, setup):
        result = get_event_pose_quality(conn, trial_id=setup["trials"][0])
        assert result["cobertura_pose"] is None
        assert result["cobertura_execucao_id"] is None
        assert result["qualidade"] is None

    def test_quality_rejects_missing_trial(self, conn):
        with pytest.raises(ValueError, match="não encontrado"):
            get_event_pose_quality(conn, trial_id=-1)

    def test_entry_roundtrip_retains_confirmation_discovery_hesitation_and_totals(
        self, conn, setup
    ):
        trial = setup["trials"][0]
        execution = _execution(conn, setup)
        event_id = _insert(
            conn,
            trial_id=trial,
            hole_id=setup["hole"],
            execucao_id=execution,
            details=ENTRY_DETAILS,
        )
        (event,) = list_hole_events(conn, trial_id=trial, execucao_id=execution)
        assert event.id == event_id
        assert event.details == ENTRY_DETAILS
        assert event.t_s == 2.0
        assert event.details["confirmed_at_s"] > event.t_s

    def test_us11_insert_and_database_default_remain_empty_objects(self, conn, setup):
        trial = setup["trials"][0]
        execution = _execution(conn, setup)
        _insert(
            conn,
            trial_id=trial,
            hole_id=setup["hole"],
            execucao_id=execution,
            tipo="descoberta",
            quadro=10,
            t_s=0.4,
        )
        conn.execute(
            """
            INSERT INTO evento_buraco (trial_id, hole_id, execucao_id, tipo, quadro, t_s)
            VALUES (%s, %s, %s, 'entrada', 50, 2.0)
            """,
            (trial, setup["hole"], execution),
        )
        events = list_hole_events(conn, trial_id=trial)
        assert [event.tipo for event in events] == ["descoberta", "entrada"]
        assert [event.details for event in events] == [{}, {}]

    def test_orphan_entry_is_preserved_as_issue_without_fabricated_discovery(self, conn, setup):
        trial = setup["trials"][0]
        details = dict(
            ENTRY_DETAILS,
            discovery_quadro=None,
            discovery_t_s=None,
            delta_latency=None,
            delta_distance_cm=None,
            issues=["entrada_sem_descoberta"],
        )
        _insert(
            conn,
            trial_id=trial,
            hole_id=setup["hole"],
            execucao_id=_execution(conn, setup),
            details=details,
        )
        (event,) = list_hole_events(conn, trial_id=trial)
        assert event.details == details

    def test_execution_filter_keeps_reprocessing_details_separate(self, conn, setup):
        trial = setup["trials"][0]
        first, second = _execution(conn, setup), _execution(conn, setup)
        for execution, duration in ((first, 1.6), (second, 1.8)):
            _insert(
                conn,
                trial_id=trial,
                hole_id=setup["hole"],
                execucao_id=execution,
                details=dict(ENTRY_DETAILS, delta_latency=duration),
            )
        assert len(list_hole_events(conn, trial_id=trial)) == 2
        (event,) = list_hole_events(conn, trial_id=trial, execucao_id=second)
        assert event.details["delta_latency"] == 1.8

    def test_event_cannot_reference_execution_from_another_trial(self, conn, setup):
        other = _execution(conn, setup, trial_index=1)
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            _insert(
                conn,
                trial_id=setup["trials"][0],
                hole_id=setup["hole"],
                execucao_id=other,
                details=ENTRY_DETAILS,
            )

    def test_execution_and_event_can_be_rolled_back_together(self, conn, setup):
        execution = _execution(conn, setup)
        event_id = _insert(
            conn,
            trial_id=setup["trials"][0],
            hole_id=setup["hole"],
            execucao_id=execution,
            details=ENTRY_DETAILS,
        )
        conn.rollback()
        assert (
            conn.execute("SELECT id FROM execucao WHERE id = %s", (execution,)).fetchone() is None
        )
        assert (
            conn.execute(
                "SELECT id FROM evento_buraco WHERE id = %s",
                (event_id,),
            ).fetchone()
            is None
        )

    @pytest.mark.parametrize("details", [[], "invalid", 1, None])
    def test_database_requires_json_object_even_without_repository(self, conn, setup, details):
        execution = _execution(conn, setup)
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                """
                INSERT INTO evento_buraco
                    (trial_id, hole_id, execucao_id, tipo, quadro, t_s, details)
                VALUES (%s, %s, %s, 'entrada', 50, 2.0, %s)
                """,
                (setup["trials"][0], setup["hole"], execution, Jsonb(details)),
            )
