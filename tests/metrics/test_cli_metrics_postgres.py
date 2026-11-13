"""US-18 de ponta a ponta com PostgreSQL e Parquet reais, só com fixtures sintéticas.

Não é o aceite r >= 0,95 (que exige a medida manual real): verifica que
`metrics displacement` lê a série sem abrir o vídeo e grava execução + métrica juntas,
e que `metrics distance-validate` pareia o resultado atual com a referência.
Requer BARNES_TEST_DATABASE_URL migrado até 0010; conftest.py isola o banco.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import cv2
import numpy as np
import pytest
from typer.testing import CliRunner

from barnes import cli
from barnes.db.calibration import save_calibration
from barnes.db.connection import get_connection
from barnes.db.executions import get_execution, record_processing_execution
from barnes.db.maze_configs import insert_maze_config
from barnes.db.trial_results import get_trial_result
from barnes.db.trials import set_pose_coverage, set_trajectory_path
from barnes.geometry.holes import generate_holes
from barnes.io.calibration import Segment, calculate_calibration
from barnes.io.trim import interval_from_seconds
from barnes.metrics.displacement import SPEED_FPS_CAVEAT
from barnes.metrics.validation import MANUAL_COLUMNS
from barnes.pose.annotations import KEYPOINTS
from barnes.pose.dataset import file_sha256, git_revision_record
from barnes.pose.series import PoseFrames, build_series
from barnes.pose.trajectory import write_trajectory
from barnes.provenance import PACKAGE_DIR, GitState, thresholds_snapshot

pytestmark = pytest.mark.skipif(
    not os.environ.get("BARNES_DATABASE_URL"),
    reason="Requer BARNES_TEST_DATABASE_URL e migrações até 0010 aplicadas.",
)
runner = CliRunner()
FPS = 10
FRAMES = 9  # quadros 0..8, intervalo útil 0..0,8 s


def _add_trial(conn, tmp_path, experiment_id, maze_id, *, step_px, fps_variable=False):
    """Trial com série: centro do corpo andando `step_px` px por quadro em x (0,1 cm/px)."""
    marker = tmp_path / f"video-{uuid4().hex}.txt"
    marker.write_text(f"Synthetic US-18 identity {uuid4()}", encoding="utf-8")
    digest = file_sha256(marker)
    trial_id = conn.execute(
        """
        INSERT INTO trials (experiment_id, maze_config_id, filename, filepath,
            phase, day_number, trial_number_in_day, content_hash, width_px,
            height_px, fps_declared, fps_real, fps_is_variable, frame_count, duration_s,
            start_time_seconds, end_time_seconds, rotation_deg)
        VALUES (%s,%s,'synthetic.mp4',%s,'acquisition',1,1,%s,400,300,10,10,%s,9,0.9,
            0,0.8,0) RETURNING id
        """,
        (experiment_id, maze_id, str(tmp_path / "no-video.mp4"), digest, fps_variable),
    ).fetchone()[0]
    trajectory = tmp_path / f"trial_{trial_id}.parquet"
    source_id = record_processing_execution(
        conn,
        trial_id=trial_id,
        maze_config_id=maze_id,
        parameters={
            "comando": "synthetic fixture",
            "processed_interval_frames": {"start": 0, "end": FRAMES - 1},
        },
        thresholds=thresholds_snapshot(),
        git=GitState.from_record(git_revision_record(PACKAGE_DIR)),
        video_hash=digest,
        started_at=datetime.now(UTC),
        artifact_path=str(trajectory),
        metadata={"qualidade_pose": {"cobertura_minima": 0.9, "trechos_pendentes": 0}},
    )
    center = 100.0 + step_px * np.arange(FRAMES)
    offsets = {"focinho": 10.0, "centro_corpo": 0.0, "base_cauda": -10.0}
    pose = PoseFrames(
        frames=np.arange(FRAMES),
        x_px={p: center + offsets[p] for p in KEYPOINTS},
        y_px={p: np.full(FRAMES, 100.0) for p in KEYPOINTS},
        confidence={p: np.ones(FRAMES) for p in KEYPOINTS},
    )
    table = build_series(
        pose,
        trial_id=trial_id,
        execucao_id=source_id,
        expected_frames=(0, FRAMES - 1),
        fps=FPS,
        interval=interval_from_seconds(0, 0.8, FPS, manually_adjusted=True),
        fps_variable=fps_variable,
        cm_per_px=0.1,
        content_hash=digest,
        model_id="synthetic-fixture",
    )
    write_trajectory(table, trajectory)
    set_trajectory_path(conn, trial_id, str(trajectory))
    set_pose_coverage(conn, trial_id, cobertura=1, execucao_id=source_id)
    return trial_id


@pytest.fixture
def lab(tmp_path, monkeypatch):
    user_id = None
    try:
        with get_connection() as conn:
            user_id = conn.execute(
                "INSERT INTO users(email, name) VALUES(%s, 'Synthetic US18') RETURNING id",
                (f"{uuid4()}@example.test",),
            ).fetchone()[0]
            experiment_id = conn.execute(
                "INSERT INTO experiments(user_id, name) VALUES(%s, 'Synthetic') RETURNING id",
                (user_id,),
            ).fetchone()[0]
            geometry = generate_holes(
                center_x_px=200, center_y_px=150, platform_radius_px=100, hole_count=4,
                start_angle_deg=0, target_hole_number=0, hole_radius_px=5,
            )
            maze_id = insert_maze_config(
                conn, experiment_id=experiment_id, name="Synthetic US18",
                arena_diameter_cm=20, hole_diameter_cm=1, geometry=geometry,
            )
            save_calibration(
                conn,
                maze_id,
                calculate_calibration(
                    [Segment((0, 0), (100, 0), 10), Segment((0, 0), (0, 100), 10)]
                ),
                reference_video="synthetic.mp4",
                reference_frame=0,
                reference_size=(400, 300),
            )

        def add(**kwargs):
            with get_connection() as conn:
                return _add_trial(conn, tmp_path, experiment_id, maze_id, **kwargs)

        def forbid_video(*args, **kwargs):
            pytest.fail("A US-18 calcula a partir do Parquet: não deve abrir vídeo.")

        monkeypatch.setattr(cv2, "VideoCapture", forbid_video)
        yield SimpleNamespace(add=add, tmp_path=tmp_path)
    finally:
        if user_id is not None:
            with get_connection() as conn:
                conn.execute("DELETE FROM users WHERE id=%s", (user_id,))


def _displacement(trial_id):
    return runner.invoke(cli.app, ["metrics", "displacement", "--trial", str(trial_id)])


def test_displacement_records_execution_and_metric_together(lab):
    trial_id = lab.add(step_px=10.0)  # 1 cm por quadro: 8 cm em 0,8 s
    result = _displacement(trial_id)
    assert result.exit_code == 0, result.output + repr(result.exception)
    payload = json.loads(result.stdout)
    assert payload["distance_cm"] == pytest.approx(8.0)
    assert payload["mean_speed_cm_s"] == pytest.approx(10.0)
    assert payload["interpolated_fraction"] == 0
    assert payload["speed_caveat"] is None
    assert payload["colunas_exportacao"]["path_distance"] == pytest.approx(8.0)
    with get_connection() as conn:
        stored = get_trial_result(conn, trial_id)
        execution = get_execution(conn, payload["execucao_id"])
    assert stored.execucao_id == payload["execucao_id"]
    assert stored.distance_cm == pytest.approx(8.0)
    assert stored.speed_mean_cm == pytest.approx(10.0)
    assert stored.interpolated_fraction == 0
    assert stored.speed_time_base_approx is False
    assert not stored.is_stale
    assert execution.parametros["comando"] == "metrics displacement"
    assert execution.parametros["ponto"] == "centro_corpo"


def test_variable_fps_trial_gets_the_speed_caveat(lab):
    trial_id = lab.add(step_px=10.0, fps_variable=True)
    result = _displacement(trial_id)
    assert result.exit_code == 0, result.output + repr(result.exception)
    payload = json.loads(result.stdout)
    assert payload["distance_cm"] == pytest.approx(8.0)  # distância normal
    assert payload["speed_caveat"] == SPEED_FPS_CAVEAT
    assert payload["colunas_exportacao"]["speed_time_base_approx"] is True
    with get_connection() as conn:
        assert get_trial_result(conn, trial_id).speed_time_base_approx is True


def test_trial_without_series_is_refused(lab):
    trial_id = lab.add(step_px=10.0)
    with get_connection() as conn:
        conn.execute("UPDATE trials SET trajectory_path = NULL WHERE id = %s", (trial_id,))
    result = _displacement(trial_id)
    assert result.exit_code == 1
    assert "pose series" in result.output
    with get_connection() as conn:
        assert get_trial_result(conn, trial_id) is None


def test_distance_validate_pairs_current_results_with_the_manual_reference(lab):
    trials = [lab.add(step_px=step) for step in (5.0, 10.0, 20.0)]  # 4, 8 e 16 cm
    for trial_id in trials:
        assert _displacement(trial_id).exit_code == 0
    unprocessed = lab.add(step_px=10.0)
    manual = lab.tmp_path / "manual.csv"
    rows = [f"{t},{d},Sintetico,teste,2026-11-12" for t, d in zip(trials, (4.1, 7.9, 16.2))]
    rows.append(f"{unprocessed},8,Sintetico,teste,2026-11-12")
    manual.write_text(",".join(MANUAL_COLUMNS) + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    out = lab.tmp_path / "rodadas"

    result = runner.invoke(
        cli.app, ["metrics", "distance-validate", "--manual", str(manual), "--saida", str(out)]
    )
    assert result.exit_code == 0, result.output + repr(result.exception)
    record = json.loads(next(out.glob("*/correlacao.json")).read_text(encoding="utf-8"))
    assert record["status"] == "aprovado"
    assert record["n"] == 3
    assert record["r"] >= 0.95
    assert record["excluidos"] == [
        {"trial_id": unprocessed, "motivo": "trial sem métrica calculada"}
    ]
