"""Comandos de métricas que leem a série da US-09 (US-18).

`metrics displacement` calcula distância total e velocidade média a partir do Parquet
do trial, sem abrir o vídeo, e grava a execução e o resultado na mesma transação.
`metrics distance-validate` compara as distâncias gravadas com a medida manual de
referência (RN06). O `metrics process` da US-02 (CSV em pixels) continua em `cli.py`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer

from barnes.cli_events import load_trajectory_inputs
from barnes.db.connection import get_connection
from barnes.db.executions import get_execution, record_processing_execution
from barnes.db.trial_results import get_trial_result, insert_trial_result
from barnes.metrics.displacement import compute_displacement
from barnes.metrics.latency import DEFAULT_DISTANCE_POINT
from barnes.metrics.validation import (
    DistancePair,
    blocked_record,
    correlate_distances,
    load_manual_distances,
    render_markdown,
)
from barnes.pose.dataset import file_sha256, git_revision_record
from barnes.pose.trajectory import read_metadata
from barnes.provenance import PACKAGE_DIR, GitState, thresholds_snapshot

DISPLACEMENT_COMMAND = "metrics displacement"


def _write_round(directory: Path, record: dict) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=False)
    json_path = directory / "correlacao.json"
    md_path = directory / "correlacao.md"
    with json_path.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2, ensure_ascii=False, allow_nan=False)
    with md_path.open("x", encoding="utf-8") as stream:
        stream.write(render_markdown(record))
    return json_path, md_path


def register_metric_commands(metrics_app: typer.Typer, command_errors: Callable) -> None:
    """Registra os comandos da US-18 sem dependência circular com barnes.cli."""

    @metrics_app.command("displacement")
    def displacement(
        trial: Annotated[int, typer.Option("--trial", min=1, help="Id do trial (trials.id).")],
        ponto: Annotated[
            str, typer.Option("--ponto", help="Ponto do corpo usado na distancia.")
        ] = DEFAULT_DISTANCE_POINT,
        dsn: Annotated[str | None, typer.Option(help="DSN; padrao BARNES_DATABASE_URL.")] = None,
    ) -> None:
        """Distancia total (cm) e velocidade media (cm/s) do trial, a partir da serie (US-18).

        Le so a serie gerada por `barnes pose series` (nunca o video): uma distancia e
        uma velocidade por trial, sobre o intervalo util. Trechos interpolados entram
        e a fracao interpolada sai junto; com fps variavel, a velocidade sai com
        ressalva de base temporal aproximada.
        """
        started_at = datetime.now(UTC)
        with command_errors():
            inputs = load_trajectory_inputs(trial, dsn)
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
                # Execução e métrica na mesma transação: nunca uma sem a outra (US-27).
                execucao_id = record_processing_execution(
                    conn,
                    trial_id=trial,
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
                    trial,
                    execucao_id=execucao_id,
                    distance_cm=result.distance_cm,
                    speed_mean_cm=result.mean_speed_cm_s,
                    route_efficiency=None,
                    px_per_10cm_used=meta["px_per_10cm"],
                    calculated_at=datetime.now(UTC),
                    interpolated_fraction=result.interpolated_fraction,
                )
            if not git.reproducible:
                typer.echo(
                    f"Aviso: execução #{execucao_id} registrada sem commit limpo — o "
                    "resultado não é reproduzível pelo commit.",
                    err=True,
                )
            quality = inputs.quality.get("qualidade")
            if quality == "insuficiente":
                typer.echo(
                    f"Aviso: trial #{trial} com QUALIDADE DE POSE INSUFICIENTE (US-10 RN06) — "
                    "a marcação vai junto das métricas.",
                    err=True,
                )
            elif quality == "revisao_pendente":
                typer.echo(
                    f"Aviso: trial #{trial} tem trechos de pose ainda não revisados — rode "
                    f"`barnes pose review --trial {trial}`.",
                    err=True,
                )
            if result.speed_caveat:
                typer.echo(f"Ressalva: {result.speed_caveat}", err=True)
            for aviso in result.avisos:
                typer.echo(f"Aviso: {aviso}", err=True)
            typer.echo(
                json.dumps(
                    {
                        "trial_id": trial,
                        "execucao_id": execucao_id,
                        **asdict(result),
                        "colunas_exportacao": result.as_export_columns(),
                        "cobertura_pose": inputs.quality.get("cobertura_pose"),
                        "qualidade_pose": quality or "nao_avaliada",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )

    @metrics_app.command("distance-validate")
    def distance_validate(
        manual: Annotated[
            Path | None,
            typer.Option(
                "--manual",
                help="CSV trial_id,distance_cm_manual,observador,metodo,data (referencia).",
            ),
        ] = None,
        saida: Annotated[
            Path, typer.Option("--saida", help="Diretorio das rodadas de comparacao.")
        ] = Path("data/validation/distance"),
        dsn: Annotated[str | None, typer.Option(help="DSN; padrao BARNES_DATABASE_URL.")] = None,
    ) -> None:
        """Correlaciona a distancia automatica com a medida manual: aceite r >= 0,95 (US-18).

        Usa o resultado atual de cada trial gravado por `metrics displacement`. Sem
        referencia manual, registra a rodada como bloqueada e sai com codigo 2.
        """
        with command_errors():
            directory = saida / f"distance-{uuid4().hex}"
            if manual is None or not manual.is_file():
                record = blocked_record("referência manual de distância não entregue")
                json_path, _ = _write_round(directory, record)
                typer.echo(f"Bloqueado: referência manual não entregue. Registro: {json_path}")
                raise typer.Exit(code=2)
            reference = load_manual_distances(manual)
            pairs: list[DistancePair] = []
            excluded: list[tuple[int, str]] = []
            with get_connection(dsn) as conn:
                for row in reference:
                    stored = get_trial_result(conn, row.trial_id)
                    if stored is None:
                        excluded.append((row.trial_id, "trial sem métrica calculada"))
                        continue
                    command = (get_execution(conn, stored.execucao_id).parametros or {}).get(
                        "comando"
                    )
                    if command != DISPLACEMENT_COMMAND:
                        excluded.append(
                            (row.trial_id, f"resultado atual veio de '{command}', não da série")
                        )
                    elif stored.distance_cm is None:
                        excluded.append((row.trial_id, "distância não calculada (sem pose)"))
                    elif stored.is_stale:
                        excluded.append((row.trial_id, "resultado obsoleto (recalibração)"))
                    else:
                        pairs.append(DistancePair(row.trial_id, row.distance_cm, stored.distance_cm))
            result = correlate_distances(pairs, excluded=excluded)
            record = result.as_record() | {
                "manual": str(manual),
                "manual_sha256": file_sha256(manual),
                "criado_em": datetime.now(UTC).isoformat(),
            }
            json_path, md_path = _write_round(directory, record)
            typer.echo(
                f"n = {result.n} · r = {result.r:.4f} (critério r >= {result.limiar:.2f}): "
                f"{record['status']}. Viés médio {result.vies_medio_cm:+.2f} cm.\n"
                f"Rodada: {json_path}\nRelatório: {md_path}"
            )
            for trial_id, motivo in excluded:
                typer.echo(f"Fora da comparação: trial {trial_id} — {motivo}", err=True)
            if not result.aprovado:
                raise typer.Exit(code=2)
