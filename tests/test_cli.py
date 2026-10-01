"""CLI integration with real video decoding/SQLite; only mouse interaction is mocked."""

import json

import cv2
import numpy as np
import pytest
from typer.testing import CliRunner

from barnes import cli
from barnes.db import CalibrationRepository
from barnes.io.calibration_ui import CalibrationCancelled

runner = CliRunner()


@pytest.fixture
def video(tmp_path):
    path = tmp_path / "reference.avi"
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.line(frame, (10, 10), (210, 10), (255, 255, 255), 2)
    cv2.line(frame, (10, 30), (10, 230), (255, 255, 255), 2)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (640, 480))
    assert writer.isOpened(), "O ambiente deve conseguir gravar o vídeo sintético MJPG."
    try:
        for _ in range(3):
            writer.write(frame)
    finally:
        writer.release()
    return path


@pytest.fixture
def args(tmp_path, video, monkeypatch):
    monkeypatch.setattr(
        cli,
        "collect_segments",
        lambda *args, **kwargs: (((10, 10), (210, 10)), ((10, 30), (10, 230))),
    )
    return [
        "--database",
        str(tmp_path / "scales.sqlite3"),
        "--video",
        str(video),
        "--orientation",
        "camera-day-1",
    ]


def calibrate(args, length="20"):
    result = runner.invoke(
        cli.app, ["calibrate", *args, "--length-1-cm", length, "--length-2-cm", length]
    )
    assert result.exit_code == 0, result.output + repr(result.exception)
    return result


def test_cli_full_calibration_reuse_validation_and_recalibration(args, tmp_path, monkeypatch):
    output = calibrate(args)
    assert "0.1 cm/px" in output.output
    trajectory = tmp_path / "trajectory.csv"
    trajectory.write_text("x_px,y_px,time_s\n10,10,0\n40,50,2\n70,90,4\n", encoding="utf-8")
    executions = []
    for trial in ("trial-1", "trial-2"):
        result = runner.invoke(
            cli.app,
            [
                "process",
                *args,
                "--trial",
                trial,
                "--trajectory",
                str(trajectory),
                "--ideal-distance-px",
                "80",
            ],
        )
        assert result.exit_code == 0, result.output + repr(result.exception)
        executions.append(json.loads(result.output))
    assert executions[0]["calibration_id"] == executions[1]["calibration_id"]
    assert executions[0]["metrics"]["distance_cm"] == pytest.approx(10)
    assert executions[0]["metrics"]["mean_speed_cm_s"] == pytest.approx(2.5)
    assert executions[0]["metrics"]["route_efficiency"] == pytest.approx(0.8)

    with monkeypatch.context() as scoped:
        scoped.setattr(cli, "collect_segments", lambda *a, **k: (((300, 100), (450, 100)),))
        checked = runner.invoke(cli.app, ["verify-scale", *args, "--length-cm", "15"])
        assert checked.exit_code == 0, checked.output
        assert "Verificação aceita" in checked.output

    calibrate(args, length="40")
    with CalibrationRepository(args[1]) as repository:
        old = repository.get_execution(executions[0]["id"])
        assert not old.is_valid
        assert old.metrics["distance_cm"] == pytest.approx(10)
        assert old.calibration_id == executions[0]["calibration_id"]
    result = runner.invoke(
        cli.app, ["process", *args, "--trial", "trial-1", "--trajectory", str(trajectory)]
    )
    assert result.exit_code == 0
    updated = json.loads(result.output)
    assert updated["metrics"]["distance_cm"] == pytest.approx(20)
    assert updated["is_valid"]
    assert updated["calibration_id"] != executions[0]["calibration_id"]
    history = runner.invoke(
        cli.app, ["scale", "--database", args[1], "--orientation", "camera-day-1", "--history"]
    )
    assert history.exit_code == 0
    assert "versão=1" in history.output and "substituída" in history.output
    assert "versão=2" in history.output and "ativa" in history.output
    result = runner.invoke(cli.app, ["executions", "--database", args[1], "--trial", "trial-1"])
    assert result.exit_code == 0
    assert len(json.loads(result.output)) == 2


def test_process_without_scale_fails_before_opening_inputs(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Sem calibração não deve abrir o vídeo.")

    monkeypatch.setattr(cli, "read_reference_frame", forbidden)
    result = runner.invoke(
        cli.app,
        [
            "process",
            "--database",
            str(tmp_path / "empty.sqlite3"),
            "--orientation",
            "camera-new",
            "--trial",
            "trial",
            "--video",
            "missing.mp4",
            "--trajectory",
            "missing.csv",
        ],
    )
    assert result.exit_code == 1
    assert "camera-new" in result.output and "exige calibração" in result.output


def test_failed_calibration_preserves_previous_scale_and_valid_runs(args):
    calibrate(args)
    with CalibrationRepository(args[1]) as repository:
        old = repository.require_calibration("camera-day-1")
        run = repository.record_execution("trial", old.id, {"distance_cm": 10})
    result = runner.invoke(
        cli.app, ["calibrate", *args, "--length-1-cm", "20", "--length-2-cm", "30"]
    )
    assert result.exit_code == 1
    assert "perspectiva" in result.output
    with CalibrationRepository(args[1]) as repository:
        assert repository.require_calibration("camera-day-1").id == old.id
        assert repository.get_execution(run.id).is_valid


def test_cancelled_calibration_creates_no_scale(args, monkeypatch):
    def cancel(*args, **kwargs):
        raise CalibrationCancelled("Operação cancelada.")

    monkeypatch.setattr(cli, "collect_segments", cancel)
    result = runner.invoke(
        cli.app, ["calibrate", *args, "--length-1-cm", "20", "--length-2-cm", "20"]
    )
    assert result.exit_code == 130
    with CalibrationRepository(args[1]) as repository:
        assert repository.get_active_calibration("camera-day-1") is None


def test_verification_at_exactly_three_percent_fails(args, monkeypatch):
    calibrate(args)
    monkeypatch.setattr(cli, "collect_segments", lambda *a, **k: (((300, 100), (403, 100)),))
    result = runner.invoke(cli.app, ["verify-scale", *args, "--length-cm", "10"])
    assert result.exit_code == 1
    assert "Reprovado" in result.output


def test_length_prompts_and_database_environment(args, monkeypatch):
    monkeypatch.setenv("BARNES_DATABASE", args[1])
    result = runner.invoke(cli.app, ["calibrate", *args[2:]], input="20\n20\n")
    assert result.exit_code == 0, result.output
    with CalibrationRepository(args[1]) as repository:
        assert repository.require_calibration("camera-day-1").cm_per_px == pytest.approx(0.1)


@pytest.mark.parametrize("content", ["x,y,time\n1,2,3", "x_px,y_px,time_s\n1,2,nope"])
def test_invalid_csv_is_reported_and_no_execution_saved(args, tmp_path, content):
    calibrate(args)
    path = tmp_path / "bad.csv"
    path.write_text(content, encoding="utf-8")
    result = runner.invoke(
        cli.app, ["process", *args, "--trajectory", str(path), "--trial", "trial"]
    )
    assert result.exit_code == 1
    assert "Erro:" in result.output
    with CalibrationRepository(args[1]) as repository:
        assert repository.list_executions() == []
