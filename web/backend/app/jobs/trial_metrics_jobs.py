"""Job RQ: métricas consolidadas de um trial numa ÚNICA execução (US-16..20).

Por que existe: a US-22 (`db.learning.load_learning_rows`) lê só a linha
**mais recente** de `trial_results` por trial e nunca combina execuções
(`docs/curvas-aprendizado.md`). O pipeline web gravava linhas parciais
separadas (distância num job, estratégia noutro), então a linha mais recente
nunca tinha latência, erros e distância juntos — e nenhum estágio gravava a
latência (US-16) nem os erros (US-17). Este job calcula tudo sobre a mesma
trajetória e a mesma sequência de visitação e grava uma linha completa:

- US-16 latências S→D/S→E com censura (`metrics.latency`);
- US-17 erros primários/totais (`metrics.errors`, via a regra da US-20);
- US-18 distância e velocidade média (`metrics.displacement`);
- US-19 índice de eficiência de rota (≥ 1) — só no relatório/metadata: a
  coluna `trial_results.route_efficiency` é a razão inversa 0..1 da US-02;
- US-20 estratégia e entropia (`strategy_jobs.compute_strategy_core`).

Limiares só de `configs/default.yaml`. Nada é calculado de novo aqui: são
as mesmas funções puras que a CLI e o teste da US-28 usam.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from rq import get_current_job

from barnes.cli_events import _detect, load_trajectory_inputs
from barnes.db.connection import get_connection
from barnes.db.executions import record_processing_execution
from barnes.db.jobs import mark_failed, mark_finished, mark_started
from barnes.db.trial_results import insert_trial_result
from barnes.metrics.displacement import compute_displacement
from barnes.metrics.efficiency import compute_trial_route_efficiency
from barnes.metrics.latency import (
    TargetEvent,
    compute_target_latencies,
    load_time_limit,
    target_discovery,
)
from barnes.pose.dataset import file_sha256, git_revision_record
from barnes.pose.trajectory import read_metadata
from barnes.provenance import DEFAULT_THRESHOLDS_PATH, PACKAGE_DIR, GitState, thresholds_snapshot

from .strategy_jobs import compute_strategy_core

TRIAL_METRICS_COMMAND = "web trial-metrics"


def _fail(dsn: str | None, rq_job_id: str, message: str) -> None:
    with get_connection(dsn) as conn:
        mark_failed(conn, rq_job_id, message)


def _event_bool(value: int | None) -> bool | None:
    """US-16: 1 = observado, 0 = censurado, None = não avaliado (nunca vira False)."""
    return None if value is None else bool(value)


def _finite(value):
    return value if isinstance(value, int | float) and math.isfinite(value) else None


def run_trial_metrics(
    *,
    trial_id: int,
    config: str | None = None,
    out_dir: str = "data/metrics",
    dsn: str | None = None,
) -> dict:
    job = get_current_job()
    with get_connection(dsn) as conn:
        mark_started(conn, job.id)

    started_at = datetime.now(UTC)
    config_path = Path(config) if config else DEFAULT_THRESHOLDS_PATH
    try:
        inputs = load_trajectory_inputs(trial_id, dsn)
        core = compute_strategy_core(inputs, trial_id, dsn, config_path)
        target = core.target_hole_number

        # US-16: D do alvo pelo mesmo detector/limiares dos eventos; E pelas
        # entradas já persistidas (as mesmas que formaram a sequência).
        discoveries, _ = _detect(inputs, config_path, entry=False)
        target_d = target_discovery(discoveries, target)
        target_entries = sorted(
            (entry for entry in core.entries if entry.hole_number == target),
            key=lambda entry: entry.t_s,
        )
        target_e = (
            TargetEvent.ocorreu(target_entries[0].t_s)
            if target_entries
            else TargetEvent.nao_ocorreu()
        )
        latencies = compute_target_latencies(
            inputs.table, target_d, target_e, tempo_limite_s=load_time_limit(config_path)
        )
        displacement = compute_displacement(inputs.table)
        efficiency = compute_trial_route_efficiency(
            inputs.table, latencies, geometry=inputs.geometry, cm_per_px=inputs.cm_per_px
        )

        classification = core.classification
        categoria = None if classification.categoria is None else classification.categoria.value
        meta = read_metadata(inputs.table)
        source = git_revision_record(PACKAGE_DIR)
        git = GitState.from_record(source)

        avisos = [
            *latencies.avisos,
            *core.errors.avisos,
            *classification.avisos,
            *core.entropy.avisos,
            *efficiency.avisos,
        ]
        report = {
            "schema_version": 1,
            "trial_id": trial_id,
            "created_at": started_at.isoformat(),
            "units": {"time": "s", "distance": "cm", "angle": "deg_room"},
            "time_origin": "intervalo_util",
            "model_id": meta.get("model_id"),
            "target_hole_number_platform": target,
            "latencias": latencies.as_trials_csv(),
            "erros": {
                "primary_errors": core.errors.ate_alvo,
                "total_errors": core.errors.total,
                "primary_censurado": core.errors.primary_censurado,
                "criterio": core.errors.definicao.criterio.value,
            },
            "deslocamento": asdict(displacement),
            "eficiencia_rota": efficiency.as_trial_results(),
            "estrategia": {
                "classificacao": categoria,
                "sinais": classification.sinais_auditoria(),
                "limiares": asdict(core.thresholds),
                "until_s": core.until_s,
            },
            "entropia_bits": core.entropy.bits,
            "sequencia": [
                {
                    "hole_number_platform": item.buraco_platform,
                    "angulo_sala_deg": item.angulo_deg_room,
                    "inicio_s": item.inicio_s,
                    "dwell_s": item.dwell_s,
                    "alvo": item.alvo,
                }
                for item in core.sequence.itens
            ],
            "avisos": avisos,
        }
        parameters = {
            "comando": TRIAL_METRICS_COMMAND,
            "config": str(config_path),
            "trajectory": str(inputs.trial.trajectory_path),
            "trajectory_sha256": inputs.trajectory_sha256,
            "trajectory_execucao_id": meta["execucao_id"],
            "sequence_source_execucao_id": core.source_execucao_id,
        }
        if file_sha256(inputs.trial.trajectory_path) != inputs.trajectory_sha256:
            raise ValueError("A trajetória mudou durante o cálculo; rode de novo.")

        directory = Path(out_dir) / f"trial-{trial_id}-{uuid4().hex}"
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
                    metadata={"source": source, "metricas_trial": report},
                )
                insert_trial_result(
                    conn,
                    trial_id,
                    execucao_id=execucao_id,
                    distance_cm=_finite(displacement.distance_cm),
                    speed_mean_cm=_finite(displacement.mean_speed_cm_s),
                    route_efficiency=None,
                    px_per_10cm_used=meta["px_per_10cm"],
                    calculated_at=datetime.now(UTC),
                    interpolated_fraction=displacement.interpolated_fraction,
                    primary_latency_s=latencies.primary.latency_s,
                    total_latency_s=latencies.total.latency_s,
                    primary_errors=core.errors.ate_alvo,
                    total_errors=core.errors.total,
                    primary_event=_event_bool(latencies.primary.event),
                    total_event=_event_bool(latencies.total.event),
                    entropy_bits=core.entropy.bits,
                    search_strategy=categoria,
                )
                report["execucao_id"] = execucao_id
                with (directory / "metricas.json").open("x", encoding="utf-8") as stream:
                    json.dump(report, stream, indent=2, ensure_ascii=False, default=str)
        except BaseException:
            (directory / "metricas.json").unlink(missing_ok=True)
            directory.rmdir()
            raise
    except Exception as exc:
        _fail(dsn, job.id, f"{type(exc).__name__}: {exc}")
        raise

    with get_connection(dsn) as conn:
        mark_finished(conn, job.id, execucao_id)
    return {
        "execucao_id": execucao_id,
        "primary_latency_s": latencies.primary.latency_s,
        "total_errors": core.errors.total,
        "distance_cm": displacement.distance_cm,
        "categoria": categoria,
    }
