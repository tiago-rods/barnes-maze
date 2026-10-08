"""Testes de integração de src/barnes/db/trial_results.py (US-02 RN03/RN05, US-27 RN02).

Exigem um Postgres com o schema de database/migrations/ aplicado, apontado
por BARNES_DATABASE_URL. São pulados automaticamente se a variável não
estiver definida (mesma convenção dos demais testes em tests/db/).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from barnes.db.calibration import save_calibration
from barnes.db.connection import get_connection
from barnes.db.executions import record_processing_execution
from barnes.db.trial_results import (
    get_trial_result,
    insert_trial_result,
    list_trial_result_history,
    list_trial_results,
)
from barnes.io.calibration import Segment, calculate_calibration
from barnes.provenance import GitState, ThresholdsSnapshot

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
def trial_id(conn):
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
        cur.execute(
            """
            INSERT INTO trials (
                experiment_id, maze_config_id, filename, filepath, phase,
                day_number, trial_number_in_day, content_hash, width_px,
                height_px, fps_declared, fps_real, frame_count, duration_s
            )
            VALUES (%s, %s, 't.mp4', 't.mp4', 'acquisition', 1, 1, %s, 640, 480, 30, 30, 300, 10)
            RETURNING id
            """,
            (experiment_id, maze_config_id, str(uuid4())),
        )
        return cur.fetchone()[0], maze_config_id


def _execution(conn, trial, maze_config_id):
    """Execução de processamento mínima, à qual as métricas do teste se vinculam."""
    return record_processing_execution(
        conn,
        trial_id=trial,
        maze_config_id=maze_config_id,
        parameters={"origem": "teste"},
        thresholds=ThresholdsSnapshot(values={}, sha256="0" * 64, path="teste.yaml"),
        git=GitState(commit="a" * 40, dirty=False),
        video_hash="hash",
        started_at=datetime.now(UTC),
    )


def _insert(conn, trial, maze_config_id, **metrics):
    values = {
        "distance_cm": 10.0,
        "speed_mean_cm": 2.5,
        "route_efficiency": None,
        "px_per_10cm_used": 100.0,
        "calculated_at": datetime.now(UTC),
    } | metrics
    execucao_id = _execution(conn, trial, maze_config_id)
    insert_trial_result(conn, trial, execucao_id=execucao_id, **values)
    return execucao_id


def _calibrate(conn, maze_config_id, cm_per_px=0.1):
    result = calculate_calibration(
        [
            Segment((10, 10), (110, 10), 100 * cm_per_px),
            Segment((20, 20), (20, 220), 200 * cm_per_px),
        ]
    )
    save_calibration(
        conn, maze_config_id, result, reference_video="a.mp4", reference_frame=0,
        reference_size=(640, 480),
    )
    return 10 / result.cm_per_px  # px_per_10cm


def test_get_trial_result_returns_none_when_not_processed(conn, trial_id):
    trial, _ = trial_id
    assert get_trial_result(conn, trial) is None


def test_result_is_not_stale_right_after_calculation(conn, trial_id):
    trial, maze_config_id = trial_id
    px_per_10cm = _calibrate(conn, maze_config_id)

    _insert(conn, trial, maze_config_id, route_efficiency=0.8, px_per_10cm_used=px_per_10cm)

    result = get_trial_result(conn, trial)
    assert result.distance_cm == pytest.approx(10.0)
    assert result.speed_mean_cm == pytest.approx(2.5)
    assert result.route_efficiency == pytest.approx(0.8)
    assert not result.is_stale


def test_result_is_stale_when_montagem_never_calibrated(conn, trial_id):
    trial, maze_config_id = trial_id
    _insert(conn, trial, maze_config_id, px_per_10cm_used=100.0)
    assert get_trial_result(conn, trial).is_stale


def test_result_becomes_stale_after_recalibration(conn, trial_id):
    trial, maze_config_id = trial_id
    px_per_10cm = _calibrate(conn, maze_config_id, cm_per_px=0.1)
    _insert(conn, trial, maze_config_id, px_per_10cm_used=px_per_10cm)
    assert not get_trial_result(conn, trial).is_stale

    _calibrate(conn, maze_config_id, cm_per_px=0.2)  # recalibra a mesma montagem

    assert get_trial_result(conn, trial).is_stale


def test_reprocessing_appends_history_and_current_is_latest(conn, trial_id):
    trial, maze_config_id = trial_id
    px_per_10cm = _calibrate(conn, maze_config_id)
    first = _insert(conn, trial, maze_config_id, px_per_10cm_used=px_per_10cm)
    second = _insert(
        conn, trial, maze_config_id, distance_cm=20.0, speed_mean_cm=5.0,
        route_efficiency=0.5, px_per_10cm_used=px_per_10cm,
    )

    result = get_trial_result(conn, trial)
    assert result.distance_cm == pytest.approx(20.0)
    assert result.execucao_id == second
    # Uma linha por trial, por execução: a anterior continua consultável.
    assert [row.execucao_id for row in list_trial_result_history(conn, trial)] == [second, first]
    assert sum(1 for row in list_trial_results(conn) if row.trial_id == trial) == 1
