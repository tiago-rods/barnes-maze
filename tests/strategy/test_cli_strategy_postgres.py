"""`barnes strategy classify` (US-20) de ponta a ponta, com PostgreSQL e Parquet reais.

Só fixtures sintéticas: prova que o comando lê trajetória + `evento_buraco`
sem abrir o vídeo, grava `entropy_bits`/`search_strategy` e a execução (US-27)
na mesma transação, e nunca classifica "aleatória" por omissão quando falta
sinal. Requer BARNES_TEST_DATABASE_URL migrado até a 0011; conftest.py isola
o banco.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
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
from barnes.db.hole_events import insert_hole_event
from barnes.db.maze_configs import get_hole_ids, insert_maze_config
from barnes.db.trial_results import get_trial_result
from barnes.db.trials import set_pose_coverage, set_trajectory_path
from barnes.events.entry import EntryEvent
from barnes.geometry.holes import generate_holes
from barnes.io.calibration import Segment, calculate_calibration
from barnes.io.trim import interval_from_seconds
from barnes.pose.annotations import KEYPOINTS
from barnes.pose.dataset import file_sha256, git_revision_record
from barnes.pose.series import PoseFrames, build_series
from barnes.pose.trajectory import write_trajectory
from barnes.provenance import PACKAGE_DIR, GitState, thresholds_snapshot

pytestmark = pytest.mark.skipif(
    not os.environ.get("BARNES_DATABASE_URL"),
    reason="Requer BARNES_TEST_DATABASE_URL e migrações até 0011 aplicadas.",
)
runner = CliRunner()
FPS = 10
FRAMES = 9  # quadros 0..8, intervalo útil 0..0,8 s
CM_PER_PX = 0.1
CENTER_X_CM = 200 * CM_PER_PX
CENTER_Y_CM = 150 * CM_PER_PX


def _add_trial(
    conn, tmp_path, experiment_id, maze_id, *, centro_corpo_cm, rotation_deg=0.0, valid=True
):
    """Trial com série: `centro_corpo` fixo em `centro_corpo_cm` em todos os quadros."""
    marker = tmp_path / f"video-{uuid4().hex}.txt"
    marker.write_text(f"Synthetic US-20 identity {uuid4()}", encoding="utf-8")
    digest = file_sha256(marker)
    trial_id = conn.execute(
        """
        INSERT INTO trials (experiment_id, maze_config_id, filename, filepath,
            phase, day_number, trial_number_in_day, content_hash, width_px,
            height_px, fps_declared, fps_real, frame_count, duration_s,
            start_time_seconds, end_time_seconds, rotation_deg)
        VALUES (%s,%s,'synthetic.mp4',%s,'acquisition',1,1,%s,400,300,10,10,9,0.9,
            0,0.8,%s) RETURNING id
        """,
        (experiment_id, maze_id, str(tmp_path / "no-video.mp4"), digest, rotation_deg),
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
    x_cm, y_cm = centro_corpo_cm
    x_px = {p: np.full(FRAMES, x_cm / CM_PER_PX) for p in KEYPOINTS}
    y_px = {p: np.full(FRAMES, y_cm / CM_PER_PX) for p in KEYPOINTS}
    if not valid:
        x_px["centro_corpo"] = np.full(FRAMES, np.nan)
        y_px["centro_corpo"] = np.full(FRAMES, np.nan)
    pose = PoseFrames(
        frames=np.arange(FRAMES),
        x_px=x_px,
        y_px=y_px,
        confidence={p: np.ones(FRAMES) for p in KEYPOINTS},
    )
    table = build_series(
        pose,
        trial_id=trial_id,
        execucao_id=source_id,
        expected_frames=(0, FRAMES - 1),
        fps=FPS,
        interval=interval_from_seconds(0, 0.8, FPS, manually_adjusted=True),
        fps_variable=False,
        cm_per_px=CM_PER_PX,
        content_hash=digest,
        model_id="synthetic-fixture",
    )
    write_trajectory(table, trajectory)
    set_trajectory_path(conn, trial_id, str(trajectory))
    set_pose_coverage(conn, trial_id, cobertura=1, execucao_id=source_id)
    return trial_id


def _add_entry(conn, trial_id, maze_id, hole_number, t_s, *, dwell_s=0.3):
    hole_id = get_hole_ids(conn, maze_id)[hole_number]
    execucao_id = record_processing_execution(
        conn,
        trial_id=trial_id,
        maze_config_id=maze_id,
        parameters={"comando": "synthetic fixture entradas"},
        thresholds=thresholds_snapshot(),
        git=GitState.from_record(git_revision_record(PACKAGE_DIR)),
        video_hash="hash",
        started_at=datetime.now(UTC),
    )
    event = EntryEvent(
        hole_number=hole_number,
        quadro=int(t_s * FPS),
        t_s=t_s,
        confirmed_at_s=t_s,
        delta_latency=None,
        delta_distance_cm=None,
        total_latency=None,
        total_distance_cm=None,
        discovery_quadro=None,
        discovery_t_s=None,
        dwell_s=dwell_s,
        dwell_interpolado=False,
        issues=(),
    )
    insert_hole_event(
        conn,
        trial_id=trial_id,
        hole_id=hole_id,
        execucao_id=execucao_id,
        tipo="entrada",
        quadro=event.quadro,
        t_s=event.t_s,
        details=asdict(event),
    )


@pytest.fixture
def lab(tmp_path, monkeypatch):
    user_id = None
    try:
        with get_connection() as conn:
            user_id = conn.execute(
                "INSERT INTO users(email, name) VALUES(%s, 'Synthetic US20') RETURNING id",
                (f"{uuid4()}@example.test",),
            ).fetchone()[0]
            experiment_id = conn.execute(
                "INSERT INTO experiments(user_id, name) VALUES(%s, 'Synthetic') RETURNING id",
                (user_id,),
            ).fetchone()[0]
            # 8 buracos a 45° um do outro; alvo = buraco 0.
            geometry = generate_holes(
                center_x_px=200, center_y_px=150, platform_radius_px=100, hole_count=8,
                start_angle_deg=0, target_hole_number=0, hole_radius_px=5,
            )
            maze_id = insert_maze_config(
                conn, experiment_id=experiment_id, name="Synthetic US20",
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

        def add_trial(**kwargs):
            with get_connection() as conn:
                return _add_trial(conn, tmp_path, experiment_id, maze_id, **kwargs)

        def add_entry(trial_id, hole_number, t_s, **kwargs):
            with get_connection() as conn:
                _add_entry(conn, trial_id, maze_id, hole_number, t_s, **kwargs)

        def forbid_video(*args, **kwargs):
            pytest.fail("A US-20 calcula a partir do Parquet e de evento_buraco: não deve abrir vídeo.")

        monkeypatch.setattr(cv2, "VideoCapture", forbid_video)
        yield SimpleNamespace(add_trial=add_trial, add_entry=add_entry, tmp_path=tmp_path)
    finally:
        if user_id is not None:
            with get_connection() as conn:
                conn.execute("DELETE FROM users WHERE id=%s", (user_id,))


def _classify(trial_id, out):
    return runner.invoke(
        cli.app, ["strategy", "classify", "--trial", str(trial_id), "--out", str(out)]
    )


def test_direct_trial_with_no_crossing_is_classified_spatial(lab):
    # Fora da zona central (raio 5 cm com centro_zona_raio_frac=0,5, raio da
    # plataforma 10 cm) e sem checagem antes do alvo: espacial (RN02).
    trial_id = lab.add_trial(centro_corpo_cm=(CENTER_X_CM + 8.0, CENTER_Y_CM))
    lab.add_entry(trial_id, 0, 0.5)  # buraco 0 = alvo, direto

    result = _classify(trial_id, lab.tmp_path / "out")
    assert result.exit_code == 0, result.output + repr(result.exception)
    report = json.loads(next((lab.tmp_path / "out").glob("*/estrategia.json")).read_text(encoding="utf-8"))
    assert report["classificacao"] == "spatial"
    assert report["sinais"]["cruzamentos_centro"] == 0
    assert report["sinais"]["erros_ate_alvo"] == 0
    assert report["entropia_bits"] == pytest.approx(0.0, abs=1e-9)

    with get_connection() as conn:
        stored = get_trial_result(conn, trial_id)
        execution = get_execution(conn, report["execucao_id"])
    assert stored.search_strategy == "spatial"
    assert stored.entropy_bits == pytest.approx(0.0, abs=1e-9)
    assert execution.parametros["comando"] == "strategy classify"
    assert execution.metadata["estrategia"]["classificacao"] == "spatial"


def test_trial_without_any_pose_sample_in_window_is_not_classified(lab):
    # Sem nenhuma checagem -> `until_s=None` (trial inteiro), mas sem pose
    # válida nenhuma: cruzamentos não calculados -> não classificado (RN01),
    # nunca "random" por omissão.
    trial_id = lab.add_trial(centro_corpo_cm=(CENTER_X_CM, CENTER_Y_CM), valid=False)

    result = _classify(trial_id, lab.tmp_path / "out2")
    assert result.exit_code == 2, result.output + repr(result.exception)
    report = json.loads(next((lab.tmp_path / "out2").glob("*/estrategia.json")).read_text(encoding="utf-8"))
    assert report["classificacao"] is None
    assert any("cruzamentos do centro não calculados" in aviso for aviso in report["avisos"])

    with get_connection() as conn:
        stored = get_trial_result(conn, trial_id)
    assert stored.search_strategy is None
