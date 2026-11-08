"""US-12/13 completos com PostgreSQL e Parquet reais, usando apenas fixtures sintéticas.

Não são evidência D3 ou aceite G3. Requer banco descartável configurado em
BARNES_TEST_DATABASE_URL e migrado; conftest.py isola o banco de trabalho.
"""

from __future__ import annotations

import csv
import json
import os
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import cv2
import numpy as np
import pytest
import yaml
from typer.testing import CliRunner

from barnes import cli, cli_events
from barnes.db.calibration import save_calibration
from barnes.db.connection import get_connection
from barnes.db.executions import get_execution, record_processing_execution
from barnes.db.hole_events import list_hole_events
from barnes.db.maze_configs import insert_maze_config
from barnes.db.trials import set_pose_coverage, set_trajectory_path
from barnes.geometry.holes import generate_holes
from barnes.io.calibration import Segment, calculate_calibration
from barnes.io.trim import interval_from_seconds
from barnes.pose.annotations import KEYPOINTS
from barnes.pose.dataset import file_sha256, git_revision_record
from barnes.pose.series import PoseFrames, build_series
from barnes.pose.trajectory import read_trajectory, write_trajectory
from barnes.provenance import PACKAGE_DIR, GitState, thresholds_snapshot

pytestmark = pytest.mark.skipif(
    not os.environ.get("BARNES_DATABASE_URL"),
    reason="Requer BARNES_TEST_DATABASE_URL e migrações até 0009 aplicadas.",
)
runner = CliRunner()


@pytest.fixture
def reference(tmp_path, monkeypatch):
    """Uma série com D=0 e entradas em .2/.6 s, visível a conexões da CLI."""
    config = tmp_path / "synthetic.yaml"
    values = {
        "encontrar": {"distancia_cm": 4, "angulo_graus": 30},
        "entrar": {"focinho_dentro": True, "raio_fator": 1, "duracao_minima_s": 0.2},
    }
    config.write_text(yaml.safe_dump(values), encoding="utf-8")
    marker = tmp_path / "synthetic-video-identity.txt"
    marker.write_text(f"Synthetic test identity {uuid4()}", encoding="utf-8")
    digest = file_sha256(marker)
    geometry = generate_holes(
        center_x_px=100,
        center_y_px=100,
        platform_radius_px=50,
        hole_count=4,
        start_angle_deg=0,
        target_hole_number=0,
        hole_radius_px=5,
    )
    quality = {"cobertura_minima": 0.98, "trechos_pendentes": 0}
    user_id = None
    try:
        with get_connection() as conn:
            user_id = conn.execute(
                "INSERT INTO users(email, name) VALUES(%s, 'Synthetic US12/13') RETURNING id",
                (f"{uuid4()}@example.test",),
            ).fetchone()[0]
            experiment_id = conn.execute(
                "INSERT INTO experiments(user_id, name) VALUES(%s, 'Synthetic') RETURNING id",
                (user_id,),
            ).fetchone()[0]
            maze_id = insert_maze_config(
                conn,
                experiment_id=experiment_id,
                name="Synthetic US12/13",
                arena_diameter_cm=10,
                hole_diameter_cm=1,
                geometry=geometry,
            )
            save_calibration(
                conn,
                maze_id,
                calculate_calibration(
                    [
                        Segment((0, 0), (100, 0), 10),
                        Segment((0, 0), (0, 100), 10),
                    ]
                ),
                reference_video=str(marker),
                reference_frame=0,
                reference_size=(400, 300),
            )
            trial_id = conn.execute(
                """
                INSERT INTO trials (experiment_id, maze_config_id, filename, filepath,
                    phase, day_number, trial_number_in_day, content_hash, width_px,
                    height_px, fps_declared, fps_real, frame_count, duration_s,
                    start_time_seconds, end_time_seconds, rotation_deg)
                VALUES (%s,%s,'synthetic.mp4',%s,'acquisition',1,1,%s,400,300,10,10,9,0.9,
                    0,0.8,0) RETURNING id
                """,
                (experiment_id, maze_id, str(tmp_path / "no-video-required.mp4"), digest),
            ).fetchone()[0]
            trajectory = tmp_path / "synthetic.parquet"
            source_id = record_processing_execution(
                conn,
                trial_id=trial_id,
                maze_config_id=maze_id,
                parameters={
                    "comando": "synthetic fixture",
                    "processed_interval_frames": {"start": 0, "end": 8},
                },
                thresholds=thresholds_snapshot(config),
                git=GitState.from_record(git_revision_record(PACKAGE_DIR)),
                video_hash=digest,
                started_at=datetime.now(UTC),
                artifact_path=str(trajectory),
                metadata={"qualidade_pose": quality},
            )
            nose = np.array([120, 130, 146, 149, 149, 120, 146, 149, 149], dtype=float)
            pose = PoseFrames(
                frames=np.arange(9),
                x_px={"focinho": nose, "centro_corpo": nose - 10, "base_cauda": nose - 20},
                y_px={p: np.full(9, 100.0) for p in KEYPOINTS},
                confidence={p: np.ones(9) for p in KEYPOINTS},
            )
            table = build_series(
                pose,
                trial_id=trial_id,
                execucao_id=source_id,
                expected_frames=(0, 8),
                fps=10,
                interval=interval_from_seconds(0, 0.8, 10, manually_adjusted=True),
                fps_variable=False,
                cm_per_px=0.1,
                content_hash=digest,
                model_id="synthetic-fixture",
            )
            write_trajectory(table, trajectory)
            set_trajectory_path(conn, trial_id, str(trajectory))
            set_pose_coverage(conn, trial_id, cobertura=1, execucao_id=source_id)

        def forbid_video(*args, **kwargs):
            pytest.fail("Recalcular eventos a partir do Parquet não deve abrir vídeo.")

        monkeypatch.setattr(cv2, "VideoCapture", forbid_video)
        yield SimpleNamespace(
            trial_id=trial_id,
            source_id=source_id,
            config=config,
            values=values,
            out=tmp_path / "output",
            annotations=tmp_path / "synthetic-d3.json",
            trajectory=trajectory,
        )
    finally:
        if user_id is not None:
            with get_connection() as conn:
                conn.execute("DELETE FROM users WHERE id=%s", (user_id,))


def _invoke(reference, command, *args):
    return runner.invoke(
        cli.app,
        [
            "events",
            command,
            "--trial",
            str(reference.trial_id),
            "--config",
            str(reference.config),
            "--out",
            str(reference.out),
            *map(str, args),
        ],
    )


def _annotations(reference, kind, times):
    reference.annotations.write_text(
        json.dumps(
            {
                "trial_id": reference.trial_id,
                "observer": "Synthetic test only",
                "source": "Fixture; not lab D3",
                "delivered_on": "2026-11-06",
                "time_origin": "intervalo_util",
                "events": [{"tipo": kind, "hole_number": 0, "t_s": time} for time in times],
            }
        ),
        encoding="utf-8",
    )
    return reference.annotations


def test_enter_persists_reentries_and_exports_actual_database_execution(reference):
    result = _invoke(reference, "enter")
    assert result.exit_code == 0, result.output + repr(result.exception)
    manifest = json.loads(next(reference.out.glob("*/events.json")).read_text(encoding="utf-8"))
    with get_connection() as conn:
        events = list_hole_events(conn, trial_id=reference.trial_id)
        execution = get_execution(conn, manifest["execucao_id"])
    assert [e.tipo for e in events] == ["descoberta", "entrada", "entrada"]
    assert [e.t_s for e in events] == [0, 0.2, 0.6]
    assert events[1].details["delta_latency"] == 0.2
    assert events[1].details["delta_distance_cm"] == pytest.approx(2.6)
    assert events[1].details["confirmed_at_s"] == 0.4
    assert all(e.execucao_id == execution.id for e in events)
    assert execution.limiares == reference.values
    assert execution.parametros["comando"] == "events enter"
    assert (
        execution.metadata["provenance"]["trajectory_metadata"]["execucao_id"]
        == reference.source_id
    )
    assert manifest["target"]["total_distance"] == pytest.approx(2.6)
    assert manifest["pose_quality"]["qualidade"] == "suficiente"
    with next(reference.out.glob("*/entries.csv")).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2 and all(row["execucao_id"] == str(execution.id) for row in rows)


@pytest.mark.parametrize(
    "kind,times,expected",
    [
        ("descoberta", [0.5], "passed"),
        ("descoberta", [0.5001], "divergence_review_required"),
        ("entrada", [0.5, 0.6], "passed"),
        ("entrada", [0.5001, 0.6], "divergence_review_required"),
    ],
)
def test_calibrate_round_and_database_agree(reference, kind, times, expected):
    annotation = _annotations(reference, kind, times)
    result = _invoke(reference, "calibrate", "--kind", kind, "--annotations", annotation)
    assert result.exit_code == (0 if expected == "passed" else 2), result.output
    report = json.loads(next(reference.out.glob("*.json")).read_text(encoding="utf-8"))
    with get_connection() as conn:
        execution = get_execution(conn, report["execucao_id"])
        events = list_hole_events(conn, trial_id=reference.trial_id, execucao_id=execution.id)
    assert report["status"] == execution.metadata["event_report"]["status"] == expected
    assert report["comparisons"] == execution.metadata["event_report"]["comparisons"]
    assert len(events) == (1 if kind == "descoberta" else 3)
    assert report["provenance"]["hashes"]["annotations_sha256"] == file_sha256(annotation)
    assert report["client_approval"] is False


def test_reprocessing_keeps_old_events_and_config(reference):
    assert _invoke(reference, "enter").exit_code == 0
    reference.values["entrar"]["duracao_minima_s"] = 0.3
    reference.config.write_text(yaml.safe_dump(reference.values), encoding="utf-8")
    assert _invoke(reference, "enter").exit_code == 0
    with get_connection() as conn:
        events = list_hole_events(conn, trial_id=reference.trial_id)
        execution_ids = sorted({event.execucao_id for event in events})
        first, second = [get_execution(conn, execution) for execution in execution_ids]
    assert len(events) == 4  # primeira rodada: D,E,E; segunda: somente D
    assert first.limiares["entrar"]["duracao_minima_s"] == 0.2
    assert second.limiares["entrar"]["duracao_minima_s"] == 0.3
    assert len(list(reference.out.glob("*/events.json"))) == 2


def test_entry_without_previous_discovery_is_persisted_with_issue(reference):
    reference.values["encontrar"]["distancia_cm"] = 0.01
    reference.config.write_text(yaml.safe_dump(reference.values), encoding="utf-8")
    result = _invoke(reference, "enter")
    assert result.exit_code == 2, result.output
    with get_connection() as conn:
        events = list_hole_events(conn, trial_id=reference.trial_id)
    assert len(events) == 2 and all(e.tipo == "entrada" for e in events)
    assert all(e.details["delta_latency"] is None for e in events)
    assert all(f"Trial {reference.trial_id}, buraco 0" in e.details["issues"][0] for e in events)


@pytest.mark.parametrize("command", ["enter", "calibrate"])
def test_artifact_failure_rolls_back_real_database_transaction(reference, monkeypatch, command):
    def fail(*args, **kwargs):
        raise OSError("simulated disk failure after INSERT")

    with get_connection() as conn:
        before = conn.execute(
            "SELECT id FROM execucao WHERE trial_id=%s", (reference.trial_id,)
        ).fetchall()
    monkeypatch.setattr(cli_events, "_export_entries" if command == "enter" else "save_round", fail)
    extra = (
        []
        if command == "enter"
        else [
            "--annotations",
            _annotations(reference, "descoberta", [0]),
        ]
    )
    result = _invoke(reference, command, *extra)
    assert result.exit_code == 1, result.output
    with get_connection() as conn:
        after = conn.execute(
            "SELECT id FROM execucao WHERE trial_id=%s", (reference.trial_id,)
        ).fetchall()
        assert list_hole_events(conn, trial_id=reference.trial_id) == []
    assert before == after
    assert not reference.out.exists() or list(reference.out.iterdir()) == []


@pytest.mark.parametrize("command", ["enter", "calibrate"])
def test_truncated_series_is_refused_before_new_database_results(reference, command):
    table = read_trajectory(reference.trajectory)
    write_trajectory(table.slice(2), reference.trajectory)
    extra = (
        []
        if command == "enter"
        else [
            "--annotations",
            _annotations(reference, "descoberta", [0]),
        ]
    )
    result = _invoke(reference, command, *extra)
    assert result.exit_code == 1 and "incompleta" in result.output, result.output
    with get_connection() as conn:
        assert conn.execute(
            "SELECT id FROM execucao WHERE trial_id=%s", (reference.trial_id,)
        ).fetchall() == [(reference.source_id,)]
        assert list_hole_events(conn, trial_id=reference.trial_id) == []
    assert not reference.out.exists()
