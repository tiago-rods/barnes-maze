"""CLI integration for `scale`/`metrics` (US-02): real video decoding and Postgres;
only the mouse interaction (collect_segments) is mocked.

Requires BARNES_DATABASE_URL pointing at a Postgres with the schema applied;
skipped automatically otherwise (same convention as tests/db/).
"""

from __future__ import annotations

import json
import os

import cv2
import numpy as np
import pytest
from typer.testing import CliRunner

from barnes import cli
from barnes.db.calibration import get_calibration
from barnes.db.connection import get_connection
from barnes.db.trial_results import get_trial_result
from barnes.db.trials import insert_trial
from barnes.io.calibration_ui import CalibrationCancelled
from barnes.io.video import load_trial_video

pytestmark = pytest.mark.skipif(
    not os.environ.get("BARNES_DATABASE_URL"),
    reason="Requer BARNES_DATABASE_URL apontando para um Postgres com o schema aplicado.",
)

runner = CliRunner()


def _write_video(path, size=(640, 480), frame_count=3):
    frame = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, size)
    assert writer.isOpened(), "O ambiente deve conseguir gravar o vídeo sintético mp4v."
    try:
        for _ in range(frame_count):
            writer.write(frame)
    finally:
        writer.release()


@pytest.fixture
def video(tmp_path):
    path = tmp_path / "reference.mp4"
    _write_video(path)
    return path


@pytest.fixture
def maze_config_id():
    """Cria user/experiment/maze_config num banco de teste real e comita.

    Precisa estar comitado (não só na transação do teste) porque os comandos
    de CLI abrem sua própria conexão via get_connection(dsn) — não veriam
    linhas ainda não comitadas por esta fixture. A limpeza por DELETE (em vez
    de rollback) é por isso: apagar o user em cascata leva experiment/
    maze_config/trial/trial_results com ele.
    """
    conn = get_connection()
    user_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (email, name) VALUES (%s, %s) RETURNING id",
                ("teste-cli@example.com", "Operador de teste"),
            )
            user_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO experiments (user_id, name) VALUES (%s, %s) RETURNING id",
                (user_id, "Experimento CLI"),
            )
            experiment_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO maze_configs
                    (experiment_id, name, arena_diameter_cm, hole_count, hole_diameter_cm)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (experiment_id, "montagem CLI", 90.0, 20, 5.0),
            )
            config_id = cur.fetchone()[0]
        conn.commit()
        yield config_id
    finally:
        if user_id is not None:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
        conn.close()


@pytest.fixture
def trial_id(maze_config_id, video):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT experiment_id FROM maze_configs WHERE id = %s", (maze_config_id,))
            experiment_id = cur.fetchone()[0]
        result = insert_trial(
            conn,
            experiment_id=experiment_id,
            maze_config_id=maze_config_id,
            video=load_trial_video(video),
            phase="acquisition",
            day_number=1,
            trial_number_in_day=1,
            rotation_deg=0.0,
        )
        conn.commit()
        return result
    finally:
        conn.close()


@pytest.fixture
def args(video, maze_config_id, monkeypatch):
    monkeypatch.setattr(
        cli,
        "collect_segments",
        lambda *args, **kwargs: (((10, 10), (210, 10)), ((10, 30), (10, 230))),
    )
    return ["--video", str(video), "--maze-config-id", str(maze_config_id)]


def calibrate(args, length="20"):
    result = runner.invoke(
        cli.app, ["scale", "calibrate", *args, "--length-1-cm", length, "--length-2-cm", length]
    )
    assert result.exit_code == 0, result.output + repr(result.exception)
    return result


def test_cli_full_flow_reuse_verification_and_recalibration(args, maze_config_id, trial_id, tmp_path, monkeypatch):
    output = calibrate(args)
    assert "0.1 cm/px" in output.output

    trajectory = tmp_path / "trajectory.csv"
    trajectory.write_text("x_px,y_px,time_s\n10,10,0\n40,50,2\n70,90,4\n", encoding="utf-8")
    result = runner.invoke(
        cli.app,
        [
            "metrics",
            "process",
            *args,
            "--trial",
            str(trial_id),
            "--trajectory",
            str(trajectory),
            "--ideal-distance-px",
            "80",
        ],
    )
    assert result.exit_code == 0, result.output + repr(result.exception)
    metrics = json.loads(result.output)
    assert metrics["distance_cm"] == pytest.approx(10)
    assert metrics["mean_speed_cm_s"] == pytest.approx(2.5)
    assert metrics["route_efficiency"] == pytest.approx(0.8)
    with get_connection() as conn:
        assert not get_trial_result(conn, trial_id).is_stale

    with monkeypatch.context() as scoped:
        # Só para esta chamada: scale verify pede 1 segmento, calibrate pede 2 (o mock
        # da fixture `args`) — sem escopar, o monkeypatch vazaria para a recalibração abaixo.
        scoped.setattr(cli, "collect_segments", lambda *a, **k: (((300, 100), (450, 100)),))
        checked = runner.invoke(cli.app, ["scale", "verify", *args, "--length-cm", "15"])
    assert checked.exit_code == 0, checked.output
    assert "Verificação aceita" in checked.output
    with get_connection() as conn:
        assert get_calibration(conn, maze_config_id).measured_error_pct == pytest.approx(0, abs=1)

    # O verify acima trocou a simulação por um segmento só; a calibração precisa de dois.
    monkeypatch.setattr(
        cli,
        "collect_segments",
        lambda *a, **k: (((10, 10), (210, 10)), ((10, 30), (10, 230))),
    )
    calibrate(args, length="40")  # recalibra a mesma montagem
    with get_connection() as conn:
        assert get_trial_result(conn, trial_id).is_stale  # calculado com a escala anterior

    reprocessed = runner.invoke(
        cli.app,
        ["metrics", "process", *args, "--trial", str(trial_id), "--trajectory", str(trajectory)],
    )
    assert reprocessed.exit_code == 0, reprocessed.output
    updated = json.loads(reprocessed.output)
    assert updated["distance_cm"] == pytest.approx(20)
    with get_connection() as conn:
        assert not get_trial_result(conn, trial_id).is_stale

    history = runner.invoke(cli.app, ["metrics", "executions"])
    assert history.exit_code == 0
    assert len(json.loads(history.output)) >= 1


def test_process_without_scale_fails_before_opening_video(maze_config_id, trial_id, monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("Sem calibração não deve decodificar o vídeo.")

    monkeypatch.setattr(cli, "read_frame", forbidden)
    result = runner.invoke(
        cli.app,
        [
            "metrics",
            "process",
            "--video",
            "missing.mp4",
            "--maze-config-id",
            str(maze_config_id),
            "--trial",
            str(trial_id),
            "--trajectory",
            "missing.csv",
        ],
    )
    assert result.exit_code == 2
    assert "exige calibração" in result.output


def test_cancelled_calibration_creates_no_scale(args, maze_config_id, monkeypatch):
    def cancel(*args, **kwargs):
        raise CalibrationCancelled("Operação cancelada.")

    monkeypatch.setattr(cli, "collect_segments", cancel)
    result = runner.invoke(
        cli.app, ["scale", "calibrate", *args, "--length-1-cm", "20", "--length-2-cm", "20"]
    )
    assert result.exit_code == 130
    with get_connection() as conn:
        assert get_calibration(conn, maze_config_id) is None


def test_bad_recalibration_preserves_previous_scale_and_valid_results(args, maze_config_id, trial_id, tmp_path, monkeypatch):
    calibrate(args)
    trajectory = tmp_path / "trajectory.csv"
    trajectory.write_text("x_px,y_px,time_s\n10,10,0\n40,50,2\n70,90,4\n", encoding="utf-8")
    runner.invoke(
        cli.app,
        ["metrics", "process", *args, "--trial", str(trial_id), "--trajectory", str(trajectory)],
    )

    # Segundo segmento paralelo ao primeiro: calculate_calibration rejeita antes de persistir.
    monkeypatch.setattr(
        cli, "collect_segments", lambda *a, **k: (((10, 10), (210, 10)), ((10, 100), (210, 100)))
    )
    result = runner.invoke(
        cli.app, ["scale", "calibrate", *args, "--length-1-cm", "20", "--length-2-cm", "20"]
    )
    assert result.exit_code == 1
    assert "direções diferentes" in result.output

    with get_connection() as conn:
        assert get_calibration(conn, maze_config_id).cm_per_px == pytest.approx(0.1)
        assert not get_trial_result(conn, trial_id).is_stale


@pytest.mark.parametrize("content", ["x,y,time\n1,2,3", "x_px,y_px,time_s\n1,2,nope"])
def test_invalid_csv_is_reported_and_no_result_saved(args, maze_config_id, trial_id, tmp_path, content):
    calibrate(args)
    path = tmp_path / "bad.csv"
    path.write_text(content, encoding="utf-8")
    result = runner.invoke(
        cli.app,
        ["metrics", "process", *args, "--trajectory", str(path), "--trial", str(trial_id)],
    )
    assert result.exit_code == 1
    assert "Erro:" in result.output
    with get_connection() as conn:
        assert get_trial_result(conn, trial_id) is None
