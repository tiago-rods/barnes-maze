"""Comandos com Parquet real e fronteira PostgreSQL simulada, sem dados D3 reais."""

from __future__ import annotations

import copy
import csv
import json
from dataclasses import replace
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
import yaml
from typer.testing import CliRunner

from barnes import cli, cli_events
from barnes.db.trials import StoredTrial
from barnes.geometry.holes import Hole, MazeGeometry
from barnes.io.trim import interval_from_seconds
from barnes.pose.annotations import KEYPOINTS
from barnes.pose.series import PoseFrames, build_series
from barnes.pose.trajectory import read_metadata, with_metadata, write_trajectory

runner = CliRunner()


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    config = tmp_path / "barnes.yaml"
    values = {
        "encontrar": {"distancia_cm": 4, "angulo_graus": 30, "calibrado_contra_anotacao": False},
        "entrar": {"raio_fator": 1, "duracao_minima_s": 0.2, "focinho_dentro": True},
    }
    config.write_text(yaml.safe_dump(values), encoding="utf-8")
    nose = np.array([7, 8, 9.5, 10, 10, 7, 9.5, 10, 10], dtype=float)
    pose = PoseFrames(
        frames=np.arange(len(nose)),
        x_px={"focinho": nose, "centro_corpo": nose - 1, "base_cauda": nose - 2},
        y_px={p: np.full(len(nose), 5.0) for p in KEYPOINTS},
        confidence={p: np.ones(len(nose)) for p in KEYPOINTS},
    )
    interval = interval_from_seconds(0, 0.8, 10, manually_adjusted=True)
    table = build_series(
        pose,
        trial_id=7,
        execucao_id=40,
        expected_frames=(0, 8),
        fps=10,
        interval=interval,
        fps_variable=False,
        cm_per_px=1,
        content_hash="a" * 64,
        model_id="synthetic-model",
    )
    path = write_trajectory(table, tmp_path / "trajectory.parquet")
    stored = StoredTrial(
        id=7,
        maze_config_id=3,
        width_px=100,
        height_px=100,
        interval=interval,
        filepath=tmp_path / "video-not-needed.mp4",
        content_hash="a" * 64,
        fps_real=10,
        fps_is_variable=False,
        trajectory_path=path,
    )
    state = SimpleNamespace(
        config=config,
        values=values,
        table=table,
        pose=pose,
        stored=stored,
        calibration=SimpleNamespace(cm_per_px=1.0),
        source=SimpleNamespace(
            trial_id=7, maze_config_id=3, status="concluido", video_hash="a" * 64
        ),
        out=tmp_path / "out",
        rotation=0,
        fail_commit=False,
        executions=[],
        events=[],
        quality={
            "cobertura_pose": 1,
            "cobertura_execucao_id": 40,
            "cobertura_minima": 0.98,
            "trechos_pendentes": 1,
            "qualidade": "revisao_pendente",
        },
    )

    class Connection:
        def __init__(self):
            self.executions = []
            self.events = []

        def __enter__(self):
            return self

        def __exit__(self, error_type, error, traceback):
            if error_type:
                return False
            if state.fail_commit and self.executions:
                raise RuntimeError("simulated commit failure")
            state.executions.extend(self.executions)
            state.events.extend(self.events)
            return False

    def record(conn, **kwargs):
        conn.executions.append(copy.deepcopy(kwargs))
        return 501 + len(state.executions)

    def insert(conn, **kwargs):
        conn.events.append(copy.deepcopy(kwargs))
        return len(conn.events)

    geometry = MazeGeometry(
        0,
        5,
        10,
        (
            Hole(0, 0, 10, 5, 1, True),
            Hole(1, 180, -10, 5, 1, False),
        ),
    )
    monkeypatch.setattr(cli_events, "get_connection", lambda dsn: Connection())
    monkeypatch.setattr(cli_events, "get_trial", lambda conn, trial: state.stored)
    monkeypatch.setattr(cli_events, "get_maze_config", lambda conn, maze: geometry)
    monkeypatch.setattr(cli_events, "get_hole_ids", lambda conn, maze: {0: 10, 1: 11})
    monkeypatch.setattr(cli_events, "require_calibration", lambda conn, maze: state.calibration)
    monkeypatch.setattr(cli_events, "get_execution", lambda conn, execution: state.source)
    monkeypatch.setattr(cli_events, "get_trial_rotations", lambda conn, trials: {7: state.rotation})
    monkeypatch.setattr(cli_events, "get_event_pose_quality", lambda conn, trial_id: state.quality)
    monkeypatch.setattr(cli_events, "record_processing_execution", record)
    monkeypatch.setattr(cli_events, "insert_hole_event", insert)
    monkeypatch.setattr(
        cli_events,
        "git_revision_record",
        lambda path: {
            "git_commit": "b" * 40,
            "git_dirty": False,
        },
    )

    def forbid_video(*args, **kwargs):
        pytest.fail("Recalcular eventos não deve abrir ou decodificar vídeo.")

    monkeypatch.setattr(cv2, "VideoCapture", forbid_video)
    return state


def invoke(scenario, command, *extra):
    return runner.invoke(
        cli.app,
        [
            "events",
            command,
            "--trial",
            "7",
            "--config",
            str(scenario.config),
            "--out",
            str(scenario.out),
            *map(str, extra),
        ],
    )


def d3(scenario, *, kind="descoberta", times=None, **changes):
    times = times if times is not None else ([0.0] if kind == "descoberta" else [0.2, 0.6])
    document = {
        "trial_id": 7,
        "observer": "fixture sintética",
        "source": "somente teste",
        "delivered_on": "2026-11-05",
        "time_origin": "intervalo_util",
        "events": [{"tipo": kind, "hole_number": 0, "t_s": t} for t in times],
        **changes,
    }
    path = scenario.config.parent / "synthetic-d3.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_missing_d3_is_blocked_without_touching_database(tmp_path, monkeypatch):
    def forbid(*args, **kwargs):
        pytest.fail("Bloqueio D3 não depende de conexão com banco.")

    monkeypatch.setattr(cli_events, "get_connection", forbid)
    out = tmp_path / "rounds"
    result = runner.invoke(cli.app, ["events", "calibrate", "--trial", "7", "--out", str(out)])
    assert result.exit_code == 2, result.output
    report = json.loads(next(out.glob("*.json")).read_text(encoding="utf-8"))
    assert report["status"] == "blocked_missing_d3"
    assert not report["comparisons"] and not report["client_approval"]
    assert list(out.glob("*.md"))


def test_unset_c2_fails_before_querying_database(monkeypatch):
    def forbid(*args, **kwargs):
        pytest.fail("Critérios pendentes devem ser recusados antes do banco.")

    monkeypatch.setattr(cli_events, "get_connection", forbid)
    result = runner.invoke(cli.app, ["events", "enter", "--trial", "7"])
    assert result.exit_code == 1 and "C2/G3" in result.output


def test_entry_round_trip_export_and_same_transaction_provenance(scenario):
    result = invoke(scenario, "enter")
    assert result.exit_code == 0, result.output
    assert len(scenario.executions) == 1
    assert [e["tipo"] for e in scenario.events] == ["descoberta", "entrada", "entrada"]
    assert all(e["execucao_id"] == 501 and e["trial_id"] == 7 for e in scenario.events)
    execution = scenario.executions[0]
    assert execution["thresholds"].values == scenario.values
    assert execution["parameters"]["comando"] == "events enter"
    assert execution["metadata"]["provenance"]["trajectory_metadata"]["execucao_id"] == 40
    assert execution["metadata"]["provenance"]["geometry"]["holes"][0]["radius_px"] == 1
    manifest = json.loads(next(scenario.out.glob("*/events.json")).read_text(encoding="utf-8"))
    assert manifest["target"]["total_latency"] == 0.2
    assert manifest["target"]["total_distance"] == pytest.approx(2.5)
    assert manifest["target"]["delta_latency"] == 0.2
    assert manifest["target"]["delta_distance"] == pytest.approx(2.5)
    assert manifest["entries"][0]["confirmed_at_s"] == 0.4
    assert manifest["pose_quality"]["qualidade"] == "revisao_pendente"
    with next(scenario.out.glob("*/entries.csv")).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [float(row["t_s"]) for row in rows] == [0.2, 0.6]
    assert rows[0]["delta_distance"] == "2.5"
    assert all(row["qualidade_pose"] == "revisao_pendente" for row in rows)


def test_target_respects_trial_rotation(scenario):
    scenario.rotation = 180
    result = invoke(scenario, "enter")
    assert result.exit_code == 0, result.output
    report = json.loads(next(scenario.out.glob("*/events.json")).read_text(encoding="utf-8"))
    assert report["target"]["hole_number_platform"] == 1
    assert report["target"]["total_event"] is False
    assert report["target"]["total_latency"] is None
    assert all(event["total_latency"] is None for event in report["entries"])


def test_orphan_entry_is_saved_and_exits_nonzero(scenario):
    scenario.values["encontrar"]["distancia_cm"] = 0.01
    # D só é detectado no centro do buraco (t=.3), depois do início E (.2).
    scenario.config.write_text(yaml.safe_dump(scenario.values), encoding="utf-8")
    result = invoke(scenario, "enter")
    assert result.exit_code == 2, result.output
    report = json.loads(next(scenario.out.glob("*/events.json")).read_text(encoding="utf-8"))
    assert report["status"] == "inconsistente"
    assert "Trial 7, buraco 0" in report["issues"][0]
    assert report["entries"][0]["delta_latency"] is None
    assert scenario.events[1]["details"]["issues"]


@pytest.mark.parametrize(
    "kind,times,expected",
    [
        ("descoberta", [0.5], "passed"),
        ("descoberta", [0.5001], "divergence_review_required"),
        ("entrada", [0.5, 0.6], "passed"),
        ("entrada", [0.5001, 0.6], "divergence_review_required"),
    ],
)
def test_calibration_thresholds_histories_and_evidence(scenario, kind, times, expected):
    annotation = d3(scenario, kind=kind, times=times)
    result = invoke(scenario, "calibrate", "--kind", kind, "--annotations", annotation)
    assert result.exit_code == (0 if expected == "passed" else 2), result.output
    path = next(scenario.out.glob("*.json"))
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["status"] == expected
    assert report["execucao_id"] == 501
    assert report["client_approval"] is False
    assert report["provenance"]["thresholds"]["values"] == scenario.values
    assert report["provenance"]["hashes"]["annotations_sha256"]
    original = path.read_bytes()
    second = invoke(scenario, "calibrate", "--kind", kind, "--annotations", annotation)
    assert second.exit_code == result.exit_code
    assert len(list(scenario.out.glob("*.json"))) == 2
    assert path.read_bytes() == original
    assert [e["parameters"]["comando"] for e in scenario.executions] == ["events calibrate"] * 2


def test_correct_timing_does_not_hide_consistency_failure(scenario):
    scenario.values["encontrar"]["distancia_cm"] = 0.01
    scenario.config.write_text(yaml.safe_dump(scenario.values), encoding="utf-8")
    result = invoke(
        scenario, "calibrate", "--kind", "entrada", "--annotations", d3(scenario, kind="entrada")
    )
    assert result.exit_code == 2, result.output
    report = json.loads(next(scenario.out.glob("*.json")).read_text(encoding="utf-8"))
    assert report["timing_status"] == "passed"
    assert report["status"] == "divergence_review_required" and not report["passed"]
    assert report["consistency_issues"]
    assert "Inconsistências" in next(scenario.out.glob("*.md")).read_text(encoding="utf-8")
    assert len(scenario.executions) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"trial_id": 8},
        {"video_sha256": "c" * 64},
        {"events": [{"tipo": "descoberta", "hole_number": 99, "t_s": 0.2}]},
        {"events": [{"tipo": "descoberta", "hole_number": 0, "t_s": 10}]},
    ],
)
def test_wrong_d3_context_is_rejected_before_writing(scenario, change):
    result = invoke(scenario, "calibrate", "--annotations", d3(scenario, **change))
    assert result.exit_code == 1, result.output
    assert not scenario.executions and not scenario.events and not scenario.out.exists()


@pytest.mark.parametrize("change", ["trial", "video", "scale", "interval", "execution", "time"])
def test_stale_or_cross_trial_trajectory_is_rejected(scenario, change):
    if change == "trial":
        meta = read_metadata(scenario.table) | {"trial_id": 8}
        table = scenario.table.set_column(0, "trial_id", scenario.table.column("trial_id"))
        # Keep original schema to let the contract detect conflicting column/metadata identity.
        import pyarrow.parquet as pq

        pq.write_table(with_metadata(table, meta), scenario.stored.trajectory_path)
    elif change == "video":
        scenario.stored = replace(scenario.stored, content_hash="d" * 64)
    elif change == "scale":
        scenario.calibration.cm_per_px = 0.5
    elif change == "interval":
        scenario.stored = replace(
            scenario.stored, interval=interval_from_seconds(0, 1, 10, manually_adjusted=True)
        )
    elif change == "execution":
        scenario.source.trial_id = 8
    else:
        import pyarrow as pa

        index = scenario.table.schema.get_field_index("t_s")
        table = scenario.table.set_column(index, "t_s", pa.array(np.arange(9) / 5))
        write_trajectory(table, scenario.stored.trajectory_path)
    result = invoke(scenario, "enter")
    assert result.exit_code == 1, result.output
    assert not scenario.executions and not scenario.out.exists()


@pytest.mark.parametrize("command", ["enter", "calibrate"])
def test_commit_failure_removes_only_new_artifacts(scenario, command):
    scenario.out.mkdir()
    sentinel = scenario.out / "previous.md"
    sentinel.write_text("previous evidence", encoding="utf-8")
    scenario.fail_commit = True
    extra = ["--annotations", d3(scenario)] if command == "calibrate" else []
    result = invoke(scenario, command, *extra)
    assert result.exit_code == 1, result.output
    assert not scenario.executions and not scenario.events
    assert list(scenario.out.iterdir()) == [sentinel]


def test_export_failure_rolls_back_events(scenario, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("simulated export failure")

    monkeypatch.setattr(cli_events, "_export_entries", fail)
    result = invoke(scenario, "enter")
    assert result.exit_code == 1, result.output
    assert not scenario.executions and not scenario.events
    assert list(scenario.out.iterdir()) == []


def test_evidence_appends_once_without_implying_g3_acceptance(scenario):
    result = invoke(scenario, "calibrate", "--annotations", d3(scenario))
    assert result.exit_code == 0, result.output
    document = scenario.config.parent / "definitions.md"
    document.write_text("# Existing definitions\nG3: pendente\n", encoding="utf-8")
    args = [
        "events",
        "calibration-evidence",
        str(next(scenario.out.glob("*.json"))),
        "--document",
        str(document),
    ]
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 0, result.output
    original = document.read_bytes()
    assert "G3: pendente" in document.read_text(encoding="utf-8")
    assert "não concedido" in document.read_text(encoding="utf-8")
    assert runner.invoke(cli.app, args).exit_code == 1
    assert document.read_bytes() == original


@pytest.mark.parametrize("command", ["enter", "calibrate"])
def test_invalid_yaml_reports_error_without_traceback(scenario, command):
    scenario.config.write_text("entrar: [", encoding="utf-8")
    result = invoke(scenario, command)
    assert result.exit_code == 1 and "YAML" in result.output


def test_all_new_help_commands_render_in_windows_console():
    for command in ("enter", "calibrate", "calibration-evidence"):
        result = runner.invoke(cli.app, ["events", command, "--help"])
        assert result.exit_code == 0, result.output
