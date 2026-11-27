"""Job RQ: distância total e velocidade média a partir da trajetória (US-18).

Mesma sequência que `cli_metrics.py`'s `displacement` já executa.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from rq import get_current_job

from barnes.cli_events import load_trajectory_inputs
from barnes.db.connection import get_connection
from barnes.db.executions import record_processing_execution
from barnes.db.jobs import mark_failed, mark_finished, mark_started
from barnes.db.trial_results import insert_trial_result
from barnes.metrics.displacement import compute_displacement
from barnes.metrics.latency import DEFAULT_DISTANCE_POINT
from barnes.pose.dataset import file_sha256, git_revision_record
from barnes.pose.trajectory import read_metadata
from barnes.provenance import PACKAGE_DIR, GitState, thresholds_snapshot

DISPLACEMENT_COMMAND = "metrics displacement"


def _fail(dsn: str | None, rq_job_id: str, message: str) -> None:
    with get_connection(dsn) as conn:
        mark_failed(conn, rq_job_id, message)


def run_metrics_displacement(
    *, trial_id: int, ponto: str = DEFAULT_DISTANCE_POINT, dsn: str | None = None
) -> dict:
    job = get_current_job()
    with get_connection(dsn) as conn:
        mark_started(conn, job.id)

    started_at = datetime.now(UTC)
    try:
        inputs = load_trajectory_inputs(trial_id, dsn)
        meta = read_metadata(inputs.table)
        result = compute_displacement(inputs.table, ponto=ponto)
        trajectory = inputs.trial.trajectory_path
        source = git_revision_record(PACKAGE_DIR)
        git = GitState.from_record(source)
        parameters = {
            "comando": DISPLACEMENT_COMMAND,
            "trajectory": str(trajectory),
            "trajectory_sha256": inputs.trajectory_sha256,
            "trajectory_execucao_id": meta["execucao_id"],
            "ponto": ponto,
            "px_per_10cm": meta["px_per_10cm"],
            "interval": asdict(inputs.trial.interval),
        }
        if file_sha256(trajectory) != inputs.trajectory_sha256:
            raise ValueError("A trajetória mudou durante o cálculo; rode de novo.")
        with get_connection(dsn) as conn:
            execucao_id = record_processing_execution(
                conn,
                trial_id=trial_id,
                maze_config_id=inputs.trial.maze_config_id,
                parameters=parameters,
                thresholds=thresholds_snapshot(),
                git=git,
                video_hash=inputs.trial.content_hash,
                started_at=started_at,
                duration_seconds=(datetime.now(UTC) - started_at).total_seconds(),
                metadata={"source": source, "deslocamento": asdict(result)},
            )
            insert_trial_result(
                conn,
                trial_id,
                execucao_id=execucao_id,
                distance_cm=result.distance_cm,
                speed_mean_cm=result.mean_speed_cm_s,
                route_efficiency=None,
                px_per_10cm_used=meta["px_per_10cm"],
                calculated_at=datetime.now(UTC),
                interpolated_fraction=result.interpolated_fraction,
            )
    except Exception as exc:
        _fail(dsn, job.id, str(exc))
        raise

    with get_connection(dsn) as conn:
        mark_finished(conn, job.id, execucao_id)
    return {
        "execucao_id": execucao_id,
        "distance_cm": result.distance_cm,
        "mean_speed_cm_s": result.mean_speed_cm_s,
        "interpolated_fraction": result.interpolated_fraction,
        "reproducible": git.reproducible,
    }
