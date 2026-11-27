"""Job RQ: descoberta + entrada por buraco (US-11/12/13).

Mesma sequência que `cli_events.py`'s `enter` já executa — é o único
comando exposto: descobertas e entradas são sempre persistidas juntas,
numa execução só (a entrada depende das descobertas para o D-to-E).
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from rq import get_current_job

from barnes.cli_events import (
    _detect,
    _export_entries,
    _load_inputs,
    _provenance,
    _record,
    _snapshot,
    _unchanged,
)
from barnes.db.connection import get_connection
from barnes.db.jobs import mark_failed, mark_finished, mark_started
from barnes.events.entry import load_entry_params
from barnes.provenance import DEFAULT_THRESHOLDS_PATH

from .tracking import enqueue_tracked
from .trial_metrics_jobs import run_trial_metrics


def _fail(dsn: str | None, rq_job_id: str, message: str) -> None:
    with get_connection(dsn) as conn:
        mark_failed(conn, rq_job_id, message)


def run_events_enter(
    *,
    trial_id: int,
    config: str | None = None,
    out_dir: str = "data/events",
    dsn: str | None = None,
) -> dict:
    job = get_current_job()
    with get_connection(dsn) as conn:
        mark_started(conn, job.id)

    started_at = datetime.now(UTC)
    config_path = Path(config) if config else DEFAULT_THRESHOLDS_PATH
    try:
        snapshot = _snapshot(config_path)
        load_entry_params(config_path)
        inputs = _load_inputs(trial_id, dsn, entry=True)
        discoveries, entries = _detect(inputs, config_path, entry=True)
        provenance = _provenance(snapshot, inputs)
        target = next((e for e in entries if e.hole_number == inputs.target_hole_number), None)
        issues = [issue for e in entries for issue in e.issues]
        report = {
            "schema_version": 1,
            "trial_id": trial_id,
            "created_at": started_at.isoformat(),
            "units": {"time": "s", "distance": "cm"},
            "time_origin": "intervalo_util",
            "pose_quality": inputs.quality,
            "status": "inconsistente" if issues else "calculado_sem_aceite_manual",
            "discoveries": [asdict(e) for e in discoveries],
            "entries": [asdict(e) for e in entries],
            "issues": issues,
            "target": {
                "hole_number_platform": inputs.target_hole_number,
                "total_event": target is not None,
                "total_latency": target.total_latency if target else None,
                "total_distance": target.total_distance_cm if target else None,
                "delta_latency": target.delta_latency if target else None,
                "delta_distance": target.delta_distance_cm if target else None,
            },
            "provenance": provenance,
        }
        _unchanged(inputs, snapshot)
        directory = Path(out_dir) / f"entry-{uuid4().hex}"
        directory.mkdir(parents=True, exist_ok=False)
        try:
            with get_connection(dsn) as conn:
                execucao_id = _record(
                    conn,
                    inputs,
                    snapshot,
                    provenance,
                    discoveries,
                    entries,
                    command="events enter",
                    started_at=started_at,
                    artifact_path=directory,
                    report=report,
                )
                _export_entries(directory, inputs, execucao_id, entries, report)
        except BaseException:
            for name in ("events.json", "entries.csv"):
                (directory / name).unlink(missing_ok=True)
            directory.rmdir()
            raise
    except Exception as exc:
        _fail(dsn, job.id, str(exc))
        raise

    with get_connection(dsn) as conn:
        mark_finished(conn, job.id, execucao_id)

    # Último elo do pipeline automático: métricas consolidadas (latência,
    # erros, distância, eficiência, estratégia) precisam da sequência de
    # visitação, que só existe depois que os eventos foram gravados.
    enqueue_tracked(
        run_trial_metrics,
        {"trial_id": trial_id, "dsn": dsn},
        kind="trial_metrics",
        trial_id=trial_id,
    )

    return {
        "execucao_id": execucao_id,
        "entries": len(entries),
        "issues": issues,
        "directory": str(directory),
    }
