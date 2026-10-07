"""Auditoria US-07/US-08; integração pula sem BARNES_DATABASE_URL."""

from __future__ import annotations

import os
from unittest.mock import MagicMock
from uuid import uuid4

import psycopg
import pytest

from barnes.db.connection import get_connection
from barnes.db.pose_executions import (
    get_execution,
    get_inference_trial,
    list_executions,
    record_execution,
)
from barnes.db.trials import insert_trial
from barnes.io.video import load_trial_video


def _record(conn, **overrides):
    values = {
        "kind": "treino",
        "model_id": "sleap-montagem-1-v1",
        "maze_config_id": 1,
        "metadata": {"dataset_version": "sha256:abc", "hyperparameters": {"epochs": 10}},
    }
    values.update(overrides)
    return record_execution(conn, **values)


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"model_id": ""}, "model_id"),
        ({"model_id": "  modelo"}, "model_id"),
        ({"model_id": "../model"}, "model_id"),
        ({"model_id": "a" * 129}, "model_id"),
        ({"kind": "teste"}, "Tipo"),
        ({"status": "iniciado"}, "Status"),
        ({"duration_seconds": -1}, "duration_seconds"),
        ({"duration_seconds": float("nan")}, "duration_seconds"),
        ({"duration_seconds": float("inf")}, "duration_seconds"),
        ({"duration_seconds": True}, "duration_seconds"),
        ({"trial_id": 1}, "por montagem"),
        ({"kind": "inferencia"}, "trial_id"),
        ({"kind": "inferencia", "trial_id": 1}, "duração"),
        ({"artifact_path": " "}, "artifact_path"),
        ({"metadata": []}, "objeto JSON"),
        ({"metadata": {"error": float("nan")}}, "JSON finitos"),
        ({"metadata": {"path": object()}}, "JSON finitos"),
        ({"metadata": {"run_id": None}}, "run_id"),
        ({"metadata": {"run_id": " "}}, "run_id"),
        ({"metadata": {"run_id": "a" * 257}}, "run_id"),
    ],
)
def test_invalid_record_is_rejected_before_database_access(overrides, message):
    conn = MagicMock()
    with pytest.raises((ValueError, TypeError), match=message):
        _record(conn, **overrides)
    conn.cursor.assert_not_called()


def test_repository_never_commits_and_preserves_manifest():
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (7,)
    manifest = {"dataset_version": "sha256:abc", "machine": {"name": "lab-local"}}
    assert _record(conn, metadata=manifest) == 7
    conn.commit.assert_not_called()
    conn.rollback.assert_not_called()
    _, values = cursor.execute.call_args.args
    assert values[-1].obj == manifest


@pytest.mark.parametrize("changed", [False, True])
def test_repeated_run_id_reuses_id_only_for_identical_provenance(changed):
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    manifest = {"run_id": "training-unique", "hyperparameters": {"seed": 42}}
    existing = (12, "treino", "sleap-montagem-1-v1", 1, None, "concluido", None, None, manifest)
    cursor.fetchone.side_effect = [None, existing]
    if changed:
        with pytest.raises(ValueError, match="outra proveniência"):
            _record(conn, metadata=dict(manifest, hyperparameters={"seed": 43}))
    else:
        assert _record(conn, metadata=manifest) == 12
    conn.commit.assert_not_called()


@pytest.fixture
def conn():
    connection = get_connection()
    yield connection
    connection.rollback()
    connection.close()


@pytest.fixture
def setup_ids(conn, make_mp4):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (email, name) VALUES (%s, %s) RETURNING id",
            (f"pose-{uuid4()}@example.com", "Teste pose"),
        )
        cur.execute(
            "INSERT INTO experiments (user_id, name) VALUES (%s, %s) RETURNING id",
            (cur.fetchone()[0], "Experimento pose"),
        )
        experiment_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO maze_configs
                (experiment_id, name, arena_diameter_cm, hole_count, hole_diameter_cm)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
            """,
            (experiment_id, "Montagem pose", 90.0, 20, 5.0),
        )
        maze_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO maze_configs
                (experiment_id, name, arena_diameter_cm, hole_count, hole_diameter_cm)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
            """,
            (experiment_id, "Outra montagem", 90.0, 20, 5.0),
        )
        other_maze_id = cur.fetchone()[0]
    trial_id = insert_trial(
        conn,
        experiment_id=experiment_id,
        maze_config_id=maze_id,
        video=load_trial_video(make_mp4(frame_count=13)),
        phase="acquisition",
        day_number=1,
        trial_number_in_day=1,
        rotation_deg=0.0,
    )
    return maze_id, other_maze_id, trial_id


@pytest.mark.skipif(
    not os.environ.get("BARNES_DATABASE_URL"),
    reason="Requer BARNES_DATABASE_URL e migração 0006_pose_executions.sql aplicada.",
)
class TestPostgresPoseExecutions:
    def test_register_run_is_idempotent_but_never_changes_audit(self, conn, setup_ids):
        maze_id, _, _ = setup_ids
        manifest = {"run_id": "test-training-run", "seed": 42}
        first = _record(conn, maze_config_id=maze_id, metadata=manifest)
        assert _record(conn, maze_config_id=maze_id, metadata=manifest) == first
        with pytest.raises(ValueError, match="outra proveniência"):
            _record(conn, maze_config_id=maze_id, metadata=dict(manifest, seed=99))
        assert get_execution(conn, first).metadata == manifest

    def test_inference_trial_identity_and_interval_are_read_together(self, conn, setup_ids):
        maze_id, _, trial_id = setup_ids
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE trials SET start_time_seconds = 0.1, end_time_seconds = 0.4,
                    interval_manually_adjusted = TRUE WHERE id = %s
                """,
                (trial_id,),
            )
        trial = get_inference_trial(conn, trial_id)
        video = load_trial_video(trial.filepath)
        assert trial.id == trial_id
        assert trial.maze_config_id == maze_id
        assert trial.content_hash == video.content_hash
        assert trial.fps_real == video.fps_real
        assert trial.frame_count == video.frame_count
        assert (trial.width_px, trial.height_px) == (video.width, video.height)
        assert trial.interval.start_s == 0.1
        assert trial.interval.end_s == 0.4
        assert trial.interval.manually_adjusted is True

    def test_inference_trial_missing_interval_stays_explicit(self, conn, setup_ids):
        _, _, trial_id = setup_ids
        assert get_inference_trial(conn, trial_id).interval is None

    def test_inference_trial_missing_record_is_rejected(self, conn):
        with pytest.raises(ValueError, match="não encontrado"):
            get_inference_trial(conn, -1)

    def test_training_retains_provenance_and_is_per_montagem(self, conn, setup_ids):
        maze_id, _, _ = setup_ids
        manifest = {
            "dataset_version": "sha256:1234",
            "hyperparameters": {"epochs": 100, "seed": 42},
            "environment": {"python": "3.11.11", "sleap_nn": "0.2.0"},
            "machine": {"hostname": "laboratorio", "gpu": "NVIDIA"},
            "artifacts": {"best.ckpt": "sha256:abcd"},
            "code_commit": "abcd1234",
            "started_at": "2026-10-06T12:00:00+00:00",
            "finished_at": "2026-10-06T12:10:00+00:00",
        }
        execution_id = _record(
            conn, maze_config_id=maze_id, metadata=manifest,
            artifact_path="models/sleap-montagem-1-v1", duration_seconds=600.0,
        )
        stored = get_execution(conn, execution_id)
        assert stored.metadata == manifest
        assert stored.trial_id is None
        assert stored.maze_config_id == maze_id
        assert stored.model_id == "sleap-montagem-1-v1"
        assert stored.kind == "treino"
        assert stored.status == "concluido"
        assert stored.duration_seconds == 600.0
        assert stored.recorded_at.utcoffset() is not None

    def test_inference_records_trial_duration_and_output(self, conn, setup_ids):
        maze_id, _, trial_id = setup_ids
        execution_id = _record(
            conn, kind="inferencia", maze_config_id=maze_id, trial_id=trial_id,
            artifact_path="data/predictions/trial-1.slp", duration_seconds=0.0,
        )
        stored = get_execution(conn, execution_id)
        assert stored.trial_id == trial_id
        assert stored.duration_seconds == 0.0
        assert stored.artifact_path == "data/predictions/trial-1.slp"

    def test_failed_attempts_and_evaluations_are_independent_rows(self, conn, setup_ids):
        maze_id, _, trial_id = setup_ids
        failed = _record(
            conn, kind="inferencia", status="falhou",
            maze_config_id=maze_id, trial_id=trial_id, metadata={"error": "GPU unavailable"},
        )
        evaluated = _record(
            conn, kind="avaliacao", maze_config_id=maze_id,
            metadata={"accepted": False, "regions": {"borda": {"median_error": 0.6}}},
        )
        assert failed != evaluated
        assert get_execution(conn, failed).status == "falhou"
        assert get_execution(conn, evaluated).metadata["accepted"] is False

    def test_filters_combine_and_preserve_repeated_attempts(self, conn, setup_ids):
        maze_id, _, trial_id = setup_ids
        first = _record(conn, maze_config_id=maze_id, model_id="one")
        second = _record(
            conn, kind="avaliacao", maze_config_id=maze_id, trial_id=trial_id, model_id="one",
        )
        _record(conn, maze_config_id=maze_id, model_id="two")
        assert [r.id for r in list_executions(conn, model_id="one")] == [first, second]
        assert [r.id for r in list_executions(conn, trial_id=trial_id, model_id="one")] == [second]
        assert list_executions(conn, model_id="does-not-exist") == []

    def test_unknown_execution_is_explicit(self, conn):
        with pytest.raises(ValueError, match="não encontrada"):
            get_execution(conn, -1)

    def test_wrong_trial_montagem_is_rejected_by_database(self, conn, setup_ids):
        _, other_maze_id, trial_id = setup_ids
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            _record(
                conn, kind="inferencia", maze_config_id=other_maze_id, trial_id=trial_id,
                duration_seconds=1.5, artifact_path="data/predictions/trial.slp",
            )

    def test_missing_montagem_is_rejected(self, conn):
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            _record(conn, maze_config_id=-1)

    def test_caller_can_rollback_record(self, conn, setup_ids):
        maze_id, _, _ = setup_ids
        execution_id = _record(conn, maze_config_id=maze_id)
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM execucao WHERE id = %s", (execution_id,))
            assert cur.fetchone() is None

    def test_existing_audit_record_cannot_be_overwritten(self, conn, setup_ids):
        maze_id, _, _ = setup_ids
        execution_id = _record(conn, maze_config_id=maze_id)
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState), conn.cursor() as cur:
            cur.execute("UPDATE execucao SET model_id = 'replaced' WHERE id = %s", (execution_id,))

    @pytest.mark.parametrize("duration", [-1.0, float("inf"), float("nan")])
    def test_database_rejects_invalid_duration_without_repository(self, conn, setup_ids, duration):
        maze_id, _, _ = setup_ids
        with pytest.raises(psycopg.errors.CheckViolation), conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO execucao
                    (kind, model_id, maze_config_id, status, duration_seconds, metadata)
                VALUES ('treino', 'model', %s, 'concluido', %s, '{}')
                """,
                (maze_id, duration),
            )
