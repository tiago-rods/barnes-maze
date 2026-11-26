"""Integração de barnes.db.export (US-25) contra o Postgres de teste."""

from __future__ import annotations

import os
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import uuid4

import numpy as np
import pytest

from barnes.db.calibration import save_calibration
from barnes.db.connection import get_connection
from barnes.db.executions import record_processing_execution
from barnes.db.export import (
    ExportError,
    list_trial_ids_by_phase,
    load_export_context,
    load_identity,
    set_experiment_group,
)
from barnes.db.hole_events import insert_hole_event
from barnes.db.maze_configs import get_hole_ids, insert_maze_config
from barnes.db.trial_results import insert_trial_result
from barnes.db.trials import insert_trial, set_trajectory_path
from barnes.events.entry import EntryEvent
from barnes.geometry.holes import generate_holes
from barnes.io.calibration import Segment, calculate_calibration
from barnes.io.trim import interval_from_seconds
from barnes.io.video import load_trial_video
from barnes.pose.series import PoseFrames, build_series
from barnes.pose.trajectory import write_trajectory
from barnes.provenance import GitState, ThresholdsSnapshot

pytestmark = pytest.mark.skipif(
    not os.environ.get("BARNES_DATABASE_URL"),
    reason="Requer BARNES_TEST_DATABASE_URL apontando para um Postgres com o schema aplicado.",
)

FPS = 10.0
N_FRAMES = 51


@pytest.fixture
def conn():
    connection = get_connection()
    yield connection
    connection.rollback()
    connection.close()


@pytest.fixture
def experiment_and_maze(conn):
    with conn.cursor() as cur:
        user = cur.execute(
            "INSERT INTO users (email, name) VALUES (%s, 'Op') RETURNING id", (str(uuid4()),)
        ).fetchone()[0]
        experiment = cur.execute(
            "INSERT INTO experiments (user_id, name) VALUES (%s, 'Exp') RETURNING id", (user,)
        ).fetchone()[0]
        cur.execute(
            "INSERT INTO subjects (experiment_id, name) VALUES (%s, 'Rato 1')", (experiment,)
        )
    geometry = generate_holes(
        center_x_px=100,
        center_y_px=100,
        platform_radius_px=60,
        hole_count=8,
        start_angle_deg=0,
        target_hole_number=0,
        hole_radius_px=6,
    )
    maze_config_id = insert_maze_config(
        conn,
        experiment_id=experiment,
        name="M",
        arena_diameter_cm=90.0,
        hole_diameter_cm=5.0,
        geometry=geometry,
    )
    return experiment, maze_config_id


def _calibrate(conn, maze_config_id, cm_per_px=1.0):
    """Calibra a montagem (US-02), condição de `load_export_context` (RN04 — rota)."""
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


def _execution(conn, trial_id, maze_config_id):
    return record_processing_execution(
        conn,
        trial_id=trial_id,
        maze_config_id=maze_config_id,
        parameters={"origem": "teste"},
        thresholds=ThresholdsSnapshot(values={}, sha256="0" * 64, path="teste.yaml"),
        git=GitState(commit="a" * 40, dirty=False),
        video_hash="hash",
        started_at=datetime.now(UTC),
    )


@pytest.fixture
def trial(conn, experiment_and_maze, make_mp4, tmp_path):
    experiment_id, maze_config_id = experiment_and_maze
    _calibrate(conn, maze_config_id)
    video = load_trial_video(make_mp4("trial.mp4", frame_count=N_FRAMES))
    trial_id = insert_trial(
        conn,
        experiment_id=experiment_id,
        maze_config_id=maze_config_id,
        video=video,
        phase="acquisition",
        day_number=1,
        trial_number_in_day=1,
        rotation_deg=0.0,
        interval=interval_from_seconds(0.0, (N_FRAMES - 1) / FPS, FPS, manually_adjusted=True),
    )

    frames = np.arange(N_FRAMES)
    centro_x = frames.astype(np.float64)
    centro_y = np.zeros(N_FRAMES)
    conf = np.ones(N_FRAMES)
    pose = PoseFrames(
        frames=frames,
        x_px={"focinho": centro_x + 1.0, "centro_corpo": centro_x, "base_cauda": centro_x - 1.0},
        y_px={"focinho": centro_y, "centro_corpo": centro_y, "base_cauda": centro_y},
        confidence={"focinho": conf, "centro_corpo": conf, "base_cauda": conf},
    )
    table = build_series(
        pose,
        trial_id=trial_id,
        execucao_id=1,
        expected_frames=(0, N_FRAMES - 1),
        fps=FPS,
        interval=interval_from_seconds(0.0, (N_FRAMES - 1) / FPS, FPS, manually_adjusted=True),
        fps_variable=False,
        cm_per_px=1.0,
        content_hash=video.content_hash,
        model_id="synthetic-export-test",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    path = tmp_path / "trajetoria.parquet"
    write_trajectory(table, path)
    set_trajectory_path(conn, trial_id, str(path))
    return trial_id, maze_config_id


def test_set_experiment_group_round_trip(conn, experiment_and_maze):
    experiment_id, _ = experiment_and_maze

    set_experiment_group(conn, experiment_id, "WT")

    with conn.cursor() as cur:
        cur.execute("SELECT group_label FROM experiments WHERE id = %s", (experiment_id,))
        (group_label,) = cur.fetchone()
    assert group_label == "WT"


def test_set_experiment_group_rejects_missing_experiment(conn):
    with pytest.raises(ExportError):
        set_experiment_group(conn, 10**9, "WT")


def test_load_identity_reads_animal_group_and_phase(conn, experiment_and_maze, trial):
    experiment_id, _ = experiment_and_maze
    trial_id, _ = trial
    set_experiment_group(conn, experiment_id, "WT")

    identity = load_identity(conn, trial_id)

    assert identity.animal == "Rato 1"
    assert identity.group_label == "WT"
    assert identity.day_number == 1
    assert identity.trial_number_in_day == 1
    assert identity.phase == "acquisition"


def test_list_trial_ids_by_phase_orders_by_day_and_trial_number(conn, experiment_and_maze, make_mp4):
    experiment_id, maze_config_id = experiment_and_maze
    ids = []
    for day, trial_in_day in ((2, 1), (1, 2), (1, 1)):
        video = load_trial_video(make_mp4(f"t_{day}_{trial_in_day}.mp4", frame_count=10))
        ids.append(
            insert_trial(
                conn,
                experiment_id=experiment_id,
                maze_config_id=maze_config_id,
                video=video,
                phase="acquisition",
                day_number=day,
                trial_number_in_day=trial_in_day,
                rotation_deg=0.0,
                interval=None,
            )
        )

    ordered = list_trial_ids_by_phase(conn, experiment_id, "acquisition")

    assert ordered == [ids[2], ids[1], ids[0]]


def test_load_export_context_rejects_trial_without_entries(conn, trial):
    trial_id, _ = trial

    with pytest.raises(ExportError, match="entrada"):
        load_export_context(conn, trial_id)


def test_load_export_context_rejects_trial_without_calibration(
    conn, experiment_and_maze, make_mp4, tmp_path
):
    """RN04: a eficiência de rota complementar exige escala — vira pendência, não erro cru."""
    experiment_id, maze_config_id = experiment_and_maze
    video = load_trial_video(make_mp4("sem_escala.mp4", frame_count=N_FRAMES))
    trial_id = insert_trial(
        conn,
        experiment_id=experiment_id,
        maze_config_id=maze_config_id,
        video=video,
        phase="acquisition",
        day_number=1,
        trial_number_in_day=1,
        rotation_deg=0.0,
        interval=interval_from_seconds(0.0, (N_FRAMES - 1) / FPS, FPS, manually_adjusted=True),
    )
    frames = np.arange(N_FRAMES)
    conf = np.ones(N_FRAMES)
    centro_x = frames.astype(np.float64)
    centro_y = np.zeros(N_FRAMES)
    pose = PoseFrames(
        frames=frames,
        x_px={"focinho": centro_x + 1.0, "centro_corpo": centro_x, "base_cauda": centro_x - 1.0},
        y_px={"focinho": centro_y, "centro_corpo": centro_y, "base_cauda": centro_y},
        confidence={"focinho": conf, "centro_corpo": conf, "base_cauda": conf},
    )
    table = build_series(
        pose,
        trial_id=trial_id,
        execucao_id=1,
        expected_frames=(0, N_FRAMES - 1),
        fps=FPS,
        interval=interval_from_seconds(0.0, (N_FRAMES - 1) / FPS, FPS, manually_adjusted=True),
        fps_variable=False,
        cm_per_px=1.0,
        content_hash=video.content_hash,
        model_id="synthetic-export-test",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    path = tmp_path / "trajetoria.parquet"
    write_trajectory(table, path)
    set_trajectory_path(conn, trial_id, str(path))

    with pytest.raises(ExportError, match="calibra"):
        load_export_context(conn, trial_id)


def test_load_export_context_reconstructs_discoveries_and_entries(conn, trial):
    trial_id, maze_config_id = trial
    hole_ids = get_hole_ids(conn, maze_config_id)

    insert_hole_event(
        conn,
        trial_id=trial_id,
        hole_id=hole_ids[0],
        execucao_id=1,
        tipo="descoberta",
        quadro=30,
        t_s=3.0,
        distancia_cm=2.0,
        angulo_deg=5.0,
    )
    entry = EntryEvent(
        hole_number=0,
        quadro=35,
        t_s=3.5,
        confirmed_at_s=3.7,
        delta_latency=0.5,
        delta_distance_cm=5.0,
        total_latency=3.5,
        total_distance_cm=35.0,
        discovery_quadro=30,
        discovery_t_s=3.0,
        dwell_s=1.0,
        dwell_interpolado=False,
    )
    insert_hole_event(
        conn,
        trial_id=trial_id,
        hole_id=hole_ids[0],
        execucao_id=1,
        tipo="entrada",
        quadro=35,
        t_s=3.5,
        details=asdict(entry),
    )

    context = load_export_context(conn, trial_id)

    assert context.target_hole_number == 0
    assert len(context.discoveries) == 1
    assert context.discoveries[0].hole_number == 0
    assert context.discoveries[0].t_s == pytest.approx(3.0)
    assert len(context.entries) == 1
    assert context.entries[0].hole_number == 0
    assert context.entries[0].delta_latency == pytest.approx(0.5)
    assert context.execucao_id == 1
    assert context.cm_per_px == pytest.approx(1.0)
    assert context.search_strategy is None
    assert context.entropy_bits is None


def test_load_export_context_reads_strategy_and_entropy_from_latest_result(conn, trial):
    """US-20 persiste `search_strategy`/`entropy_bits` em `trial_results` (RN04 do card)."""
    trial_id, maze_config_id = trial
    hole_ids = get_hole_ids(conn, maze_config_id)
    insert_hole_event(
        conn,
        trial_id=trial_id,
        hole_id=hole_ids[0],
        execucao_id=1,
        tipo="entrada",
        quadro=35,
        t_s=3.5,
        details=asdict(
            EntryEvent(
                hole_number=0,
                quadro=35,
                t_s=3.5,
                confirmed_at_s=3.7,
                delta_latency=0.5,
                delta_distance_cm=5.0,
                total_latency=3.5,
                total_distance_cm=35.0,
                discovery_quadro=30,
                discovery_t_s=3.0,
                dwell_s=1.0,
                dwell_interpolado=False,
            )
        ),
    )
    strategy_execucao_id = _execution(conn, trial_id, maze_config_id)
    insert_trial_result(
        conn,
        trial_id,
        execucao_id=strategy_execucao_id,
        distance_cm=None,
        speed_mean_cm=None,
        route_efficiency=None,
        px_per_10cm_used=10.0,
        calculated_at=datetime.now(UTC),
        entropy_bits=1.75,
        search_strategy="serial",
    )

    context = load_export_context(conn, trial_id)

    assert context.search_strategy == "serial"
    assert context.entropy_bits == pytest.approx(1.75)
