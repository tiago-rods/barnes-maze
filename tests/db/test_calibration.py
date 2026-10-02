"""Testes de integração de src/barnes/db/calibration.py (US-02).

Exigem um Postgres com o schema de database/migrations/ aplicado, apontado
por BARNES_DATABASE_URL. São pulados automaticamente se a variável não
estiver definida (mesma convenção dos demais testes em tests/db/).
"""

from __future__ import annotations

import os

import pytest

from barnes.db.calibration import (
    CalibrationRequiredError,
    StoredCalibration,
    get_calibration,
    require_calibration,
    save_calibration,
    save_verification,
    validate_frame_size,
)
from barnes.db.connection import get_connection
from barnes.io.calibration import Segment, calculate_calibration

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
def maze_config_id(conn):
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
        return cur.fetchone()[0]


def _result(cm_per_px=0.1):
    return calculate_calibration(
        [
            Segment((10, 10), (110, 10), 100 * cm_per_px),
            Segment((20, 20), (20, 220), 200 * cm_per_px),
        ]
    )


def test_save_and_require_calibration_roundtrip(conn, maze_config_id):
    result = _result()
    save_calibration(
        conn,
        maze_config_id,
        result,
        reference_video="trial-1.mp4",
        reference_frame=3,
        reference_size=(640, 480),
    )

    stored = require_calibration(conn, maze_config_id)

    assert stored.cm_per_px == pytest.approx(0.1)
    assert stored.segments == result.segments
    assert (stored.reference_width, stored.reference_height) == (640, 480)
    assert stored.reference_video == "trial-1.mp4"
    assert stored.reference_frame == 3
    assert stored.measured_error_pct is None


def test_require_calibration_raises_when_missing(conn, maze_config_id):
    with pytest.raises(CalibrationRequiredError, match=rf"{maze_config_id}.*exige calibração"):
        require_calibration(conn, maze_config_id)


def test_get_calibration_returns_none_when_missing(conn, maze_config_id):
    assert get_calibration(conn, maze_config_id) is None


def test_get_calibration_raises_for_unknown_maze_config(conn):
    with pytest.raises(ValueError, match="não encontrada"):
        get_calibration(conn, 999999)


def test_recalibration_overwrites_scale_and_resets_measured_error(conn, maze_config_id):
    save_calibration(
        conn, maze_config_id, _result(0.1), reference_video="a.mp4", reference_frame=0,
        reference_size=(640, 480),
    )
    save_verification(conn, maze_config_id, 0.02)
    assert require_calibration(conn, maze_config_id).measured_error_pct == pytest.approx(2.0)

    save_calibration(
        conn, maze_config_id, _result(0.2), reference_video="b.mp4", reference_frame=0,
        reference_size=(800, 600),
    )
    recalibrated = require_calibration(conn, maze_config_id)
    assert recalibrated.cm_per_px == pytest.approx(0.2)
    assert recalibrated.reference_video == "b.mp4"
    assert recalibrated.measured_error_pct is None  # a verificação anterior não vale mais


def test_save_verification_raises_for_unknown_maze_config(conn):
    with pytest.raises(ValueError, match="não encontrada"):
        save_verification(conn, 999999, 0.01)


def test_validate_frame_size_rejects_mismatched_resolution():
    calibration = StoredCalibration(
        cm_per_px=0.1,
        calibration_date=None,
        measured_error_pct=None,
        segments=_result().segments,
        reference_video="a.mp4",
        reference_frame=0,
        reference_width=640,
        reference_height=480,
    )
    validate_frame_size(calibration, (640, 480))  # não levanta
    with pytest.raises(ValueError, match="Resolução"):
        validate_frame_size(calibration, (1280, 720))
