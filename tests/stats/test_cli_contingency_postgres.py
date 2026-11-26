"""`barnes stats contingency` (US-23) de ponta a ponta, com PostgreSQL real.

Só trials/`trial_results` sintéticos — a consulta não precisa de trajetória nem
vídeo (US-23 é puro banco). Requer BARNES_TEST_DATABASE_URL migrado; conftest.py
isola o banco.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from barnes import cli
from barnes.db.connection import get_connection
from barnes.db.executions import record_processing_execution
from barnes.db.trial_results import insert_trial_result
from barnes.provenance import GitState, ThresholdsSnapshot

pytestmark = pytest.mark.skipif(
    not os.environ.get("BARNES_DATABASE_URL"),
    reason="Requer BARNES_TEST_DATABASE_URL apontando para um Postgres com o schema aplicado.",
)
runner = CliRunner()


def _trial(conn, experiment_id, maze_config_id, *, day_number, trial_number_in_day=1):
    return conn.execute(
        """
        INSERT INTO trials (
            experiment_id, maze_config_id, filename, filepath, phase,
            day_number, trial_number_in_day, content_hash, width_px,
            height_px, fps_declared, fps_real, frame_count, duration_s
        )
        VALUES (%s, %s, 't.mp4', 't.mp4', 'acquisition', %s, %s, %s, 640, 480, 30, 30, 300, 10)
        RETURNING id
        """,
        (experiment_id, maze_config_id, day_number, trial_number_in_day, str(uuid4())),
    ).fetchone()[0]


def _classify(conn, trial_id, maze_config_id, *, search_strategy):
    execucao_id = record_processing_execution(
        conn,
        trial_id=trial_id,
        maze_config_id=maze_config_id,
        parameters={"origem": "teste"},
        thresholds=ThresholdsSnapshot(values={}, sha256="0" * 64, path="teste.yaml"),
        git=GitState(commit="a" * 40, dirty=False),
        video_hash="hash",
        started_at=datetime.now(UTC),
    )
    insert_trial_result(
        conn,
        trial_id,
        execucao_id=execucao_id,
        distance_cm=None,
        speed_mean_cm=None,
        route_efficiency=None,
        px_per_10cm_used=100.0,
        calculated_at=datetime.now(UTC),
        search_strategy=search_strategy,
    )


@pytest.fixture
def lab():
    user_id = None
    try:
        with get_connection() as conn:
            user_id = conn.execute(
                "INSERT INTO users(email, name) VALUES(%s, 'Synthetic US23') RETURNING id",
                (f"{uuid4()}@example.test",),
            ).fetchone()[0]
            experiment_id = conn.execute(
                "INSERT INTO experiments(user_id, name) VALUES(%s, 'Synthetic') RETURNING id",
                (user_id,),
            ).fetchone()[0]
            maze_config_id = conn.execute(
                """
                INSERT INTO maze_configs
                    (experiment_id, name, arena_diameter_cm, hole_count, hole_diameter_cm)
                VALUES (%s, 'M', 90.0, 20, 5.0) RETURNING id
                """,
                (experiment_id,),
            ).fetchone()[0]
            t1 = _trial(conn, experiment_id, maze_config_id, day_number=1, trial_number_in_day=1)
            t2 = _trial(conn, experiment_id, maze_config_id, day_number=1, trial_number_in_day=2)
            t3 = _trial(conn, experiment_id, maze_config_id, day_number=2, trial_number_in_day=1)
            _classify(conn, t1, maze_config_id, search_strategy="spatial")
            _classify(conn, t2, maze_config_id, search_strategy="random")
            _classify(conn, t3, maze_config_id, search_strategy="serial")
        yield SimpleNamespace(
            experiment_id=experiment_id, maze_config_id=maze_config_id, trials=(t1, t2, t3)
        )
    finally:
        if user_id is not None:
            with get_connection() as conn:
                conn.execute("DELETE FROM users WHERE id=%s", (user_id,))


def test_contingency_by_session_is_blocked_without_threshold_configured(lab, tmp_path):
    """Estado de produção real: `configs/default.yaml` tem o limiar null (G3 aberto)."""
    result = runner.invoke(
        cli.app,
        ["stats", "contingency", "--experiment-id", str(lab.experiment_id), "--out", str(tmp_path)],
    )

    assert result.exit_code == 2, result.output
    tabela = json.loads(next(tmp_path.glob("*/tabela.json")).read_text(encoding="utf-8"))
    assert tabela["dimensao"] == "sessao"
    assert tabela["linhas"] == [1, 2]
    assert tabela["total"] == 3


def test_contingency_by_session_runs_test_with_explicit_threshold(lab, tmp_path):
    config = tmp_path / "limiar.yaml"
    config.write_text("estatistica:\n  frequencia_esperada_minima: 0.1\n", encoding="utf-8")

    result = runner.invoke(
        cli.app,
        [
            "stats",
            "contingency",
            "--experiment-id",
            str(lab.experiment_id),
            "--config",
            str(config),
            "--out",
            str(tmp_path / "out"),
        ],
    )

    assert result.exit_code == 0, result.output
    record = json.loads(next((tmp_path / "out").glob("*/resultado.json")).read_text(encoding="utf-8"))
    assert record["tabela"]["total"] == 3
    assert record["teste"] is not None


def test_contingency_by_group_requires_group_label_set(lab, tmp_path):
    result = runner.invoke(
        cli.app,
        [
            "stats",
            "contingency",
            "--experiment-id",
            str(lab.experiment_id),
            "--dimensao",
            "grupo",
            "--out",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 1
    assert "grupo experimental" in result.output


def test_contingency_by_group_after_set_group(lab, tmp_path):
    with get_connection() as conn:
        conn.execute(
            "UPDATE experiments SET group_label = 'WT' WHERE id = %s", (lab.experiment_id,)
        )
    config = tmp_path / "limiar.yaml"
    config.write_text("estatistica:\n  frequencia_esperada_minima: 0.1\n", encoding="utf-8")

    result = runner.invoke(
        cli.app,
        [
            "stats",
            "contingency",
            "--experiment-id",
            str(lab.experiment_id),
            "--dimensao",
            "grupo",
            "--config",
            str(config),
            "--out",
            str(tmp_path / "out"),
        ],
    )

    assert result.exit_code == 0, result.output
    record = json.loads(next((tmp_path / "out").glob("*/resultado.json")).read_text(encoding="utf-8"))
    assert record["tabela"]["dimensao"] == "grupo"
    assert record["tabela"]["linhas"] == ["WT"]
