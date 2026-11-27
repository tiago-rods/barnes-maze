"""Job RQ: classificação de estratégia de busca (US-20).

Mesma sequência que `cli_strategy.py`'s `classify` já executa.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from rq import get_current_job

from barnes.cli_events import load_sequence_entries, load_trajectory_inputs
from barnes.db.connection import get_connection
from barnes.db.executions import record_processing_execution
from barnes.db.jobs import mark_failed, mark_finished, mark_started
from barnes.db.trial_results import insert_trial_result
from barnes.events.sequence import build_sequence, to_visit_sequence
from barnes.geometry.reference_frame import target_room_angle
from barnes.metrics.errors import compute_errors, load_error_definition
from barnes.pose.dataset import file_sha256, git_revision_record
from barnes.pose.trajectory import read_metadata
from barnes.provenance import DEFAULT_THRESHOLDS_PATH, PACKAGE_DIR, GitState, thresholds_snapshot
from barnes.strategy.classification import classify_strategy, load_strategy_thresholds
from barnes.strategy.entropy import compute_trajectory_entropy
from barnes.strategy.signals import compute_angular_adjacency, count_center_crossings

STRATEGY_COMMAND = "strategy classify"


def _fail(dsn: str | None, rq_job_id: str, message: str) -> None:
    with get_connection(dsn) as conn:
        mark_failed(conn, rq_job_id, message)


def run_strategy_classify(
    *,
    trial_id: int,
    config: str | None = None,
    out_dir: str = "data/strategy",
    dsn: str | None = None,
) -> dict:
    job = get_current_job()
    with get_connection(dsn) as conn:
        mark_started(conn, job.id)

    started_at = datetime.now(UTC)
    config_path = Path(config) if config else DEFAULT_THRESHOLDS_PATH
    try:
        thresholds = load_strategy_thresholds(config_path)
        error_definition = load_error_definition(config_path)
        inputs = load_trajectory_inputs(trial_id, dsn)
        geometry, rotation_deg, target_hole_number, entries, source_execucao_id = (
            load_sequence_entries(trial_id, dsn)
        )
        items = build_sequence(
            entries,
            geometry=geometry,
            rotation_deg=rotation_deg,
            target_hole_number=target_hole_number,
        )
        sequence = to_visit_sequence(items)
        target_angle_deg_room = target_room_angle(geometry)
        until_s = next((item.inicio_s for item in sequence.itens if item.alvo), None)

        errors = compute_errors(sequence, error_definition)
        adjacency = compute_angular_adjacency(
            sequence,
            target_angle_deg_room=target_angle_deg_room,
            adjacencia_angular_graus=thresholds.adjacencia_angular_graus,
        )
        crossings = count_center_crossings(
            inputs.table,
            geometry,
            inputs.cm_per_px,
            zona_raio_frac=thresholds.centro_zona_raio_frac,
            until_s=until_s,
        )
        entropy = compute_trajectory_entropy(
            inputs.table, geometry, inputs.cm_per_px, until_s=until_s
        )
        classification = classify_strategy(crossings, adjacency, errors, thresholds=thresholds)

        meta = read_metadata(inputs.table)
        source = git_revision_record(PACKAGE_DIR)
        git = GitState.from_record(source)
        categoria = None if classification.categoria is None else classification.categoria.value
        report = {
            "schema_version": 1,
            "trial_id": trial_id,
            "created_at": started_at.isoformat(),
            "units": {"angle": "deg_room", "time": "s"},
            "time_origin": "intervalo_util",
            "sequence_source_execucao_id": source_execucao_id,
            "until_s": until_s,
            "classificacao": categoria,
            "sinais": classification.sinais_auditoria(),
            "limiares": asdict(thresholds),
            "entropia_bits": entropy.bits,
            "entropia": asdict(entropy),
            "avisos": list(classification.avisos) + list(entropy.avisos),
        }
        parameters = {
            "comando": STRATEGY_COMMAND,
            "config": str(config_path),
            "trajectory": str(inputs.trial.trajectory_path),
            "trajectory_sha256": inputs.trajectory_sha256,
            "trajectory_execucao_id": meta["execucao_id"],
            "sequence_source_execucao_id": source_execucao_id,
            "until_s": until_s,
        }
        if file_sha256(inputs.trial.trajectory_path) != inputs.trajectory_sha256:
            raise ValueError("A trajetória mudou durante o cálculo; rode de novo.")

        directory = Path(out_dir) / f"strategy-{uuid4().hex}"
        directory.mkdir(parents=True, exist_ok=False)
        try:
            with get_connection(dsn) as conn:
                execucao_id = record_processing_execution(
                    conn,
                    trial_id=trial_id,
                    maze_config_id=inputs.trial.maze_config_id,
                    parameters=parameters,
                    thresholds=thresholds_snapshot(config_path),
                    git=git,
                    video_hash=inputs.trial.content_hash,
                    started_at=started_at,
                    duration_seconds=(datetime.now(UTC) - started_at).total_seconds(),
                    artifact_path=str(directory),
                    metadata={"source": source, "estrategia": report},
                )
                insert_trial_result(
                    conn,
                    trial_id,
                    execucao_id=execucao_id,
                    distance_cm=None,
                    speed_mean_cm=None,
                    route_efficiency=None,
                    px_per_10cm_used=meta["px_per_10cm"],
                    calculated_at=datetime.now(UTC),
                    entropy_bits=entropy.bits,
                    search_strategy=categoria,
                )
                report["execucao_id"] = execucao_id
                with (directory / "estrategia.json").open("x", encoding="utf-8") as stream:
                    json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
        except BaseException:
            (directory / "estrategia.json").unlink(missing_ok=True)
            directory.rmdir()
            raise
    except Exception as exc:
        _fail(dsn, job.id, str(exc))
        raise

    with get_connection(dsn) as conn:
        mark_finished(conn, job.id, execucao_id)
    return {
        "execucao_id": execucao_id,
        "categoria": categoria,
        "entropy_bits": entropy.bits,
        "avisos": report["avisos"],
        "directory": str(directory),
    }
