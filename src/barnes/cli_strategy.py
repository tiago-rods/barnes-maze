"""Comando de classificação de estratégia de busca (US-20).

`strategy classify` lê a trajetória (US-09) e a sequência de visitação já
persistida (`evento_buraco`, US-13/US-15), calcula os três sinais da RN02 —
cruzamentos do centro, adjacência angular e erros até o alvo (US-17) —, a
entropia da trajetória e a classificação, e grava `entropy_bits`/
`search_strategy` em `trial_results` na mesma transação da execução (US-27).
Nunca reabre o vídeo nem a pose crua (RN03 da US-15, herdada).

Os três sinais e os limiares usados vão para `execucao.metadata` e para um
relatório JSON (RN06 — auditoria caso a caso): não há colunas novas para
eles em `trial_results`, só `entropy_bits`/`search_strategy` (migração 0011
e migração 0001, respectivamente).
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

from barnes.cli_events import load_sequence_entries, load_trajectory_inputs
from barnes.db.connection import get_connection
from barnes.db.executions import record_processing_execution
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


def register_strategy_commands(strategy_app: typer.Typer, command_errors: Callable) -> None:
    """Registra os comandos da US-20 sem dependência circular com barnes.cli."""

    @strategy_app.command("classify")
    def classify(
        trial: Annotated[int, typer.Option("--trial", min=1, help="Id do trial (trials.id).")],
        config: Annotated[
            Path, typer.Option(help="YAML com as seções estrategia e erro.")
        ] = DEFAULT_THRESHOLDS_PATH,
        out: Annotated[Path, typer.Option(help="Diretório de novos relatórios.")] = Path(
            "data/strategy"
        ),
        dsn: Annotated[str | None, typer.Option(help="DSN; padrão BARNES_DATABASE_URL.")] = None,
    ) -> None:
        """Classifica a estratégia de busca (espacial/serial/aleatória) de um trial (US-20).

        Combina cruzamentos do centro, adjacência angular dos buracos
        checados e erros até o alvo (RN02), até a primeira checagem do alvo
        (ou o trial inteiro, censurado, se o alvo não foi checado — mesma
        convenção da US-17). Sem algum sinal calculado, não classifica
        (RN01): nunca cai em "aleatória" por omissão — sai com código 2.
        """
        started_at = datetime.now(UTC)
        with command_errors():
            thresholds = load_strategy_thresholds(config)
            error_definition = load_error_definition(config)
            inputs = load_trajectory_inputs(trial, dsn)
            geometry, rotation_deg, target_hole_number, entries, source_execucao_id = (
                load_sequence_entries(trial, dsn)
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
            categoria = (
                None if classification.categoria is None else classification.categoria.value
            )
            report = {
                "schema_version": 1,
                "trial_id": trial,
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
                "config": str(config),
                "trajectory": str(inputs.trial.trajectory_path),
                "trajectory_sha256": inputs.trajectory_sha256,
                "trajectory_execucao_id": meta["execucao_id"],
                "sequence_source_execucao_id": source_execucao_id,
                "until_s": until_s,
            }
            if file_sha256(inputs.trial.trajectory_path) != inputs.trajectory_sha256:
                raise ValueError("A trajetória mudou durante o cálculo; rode de novo.")

            directory = out / f"strategy-{uuid4().hex}"
            directory.mkdir(parents=True, exist_ok=False)
            try:
                with get_connection(dsn) as conn:
                    execucao_id = record_processing_execution(
                        conn,
                        trial_id=trial,
                        maze_config_id=inputs.trial.maze_config_id,
                        parameters=parameters,
                        thresholds=thresholds_snapshot(config),
                        git=git,
                        video_hash=inputs.trial.content_hash,
                        started_at=started_at,
                        duration_seconds=(datetime.now(UTC) - started_at).total_seconds(),
                        artifact_path=str(directory),
                        metadata={"source": source, "estrategia": report},
                    )
                    insert_trial_result(
                        conn,
                        trial,
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

            if not git.reproducible:
                typer.echo(
                    f"Aviso: execução #{execucao_id} registrada sem commit limpo — o "
                    "resultado não é reproduzível pelo commit.",
                    err=True,
                )
            for aviso in report["avisos"]:
                typer.echo(f"Aviso: {aviso}", err=True)
            typer.echo(
                f"Trial #{trial}: classificação = {categoria or 'não classificado'}; "
                f"entropia = {entropy.bits if entropy.bits is not None else 'não calculada'} bits. "
                f"Execução #{execucao_id}. Relatório: {directory}"
            )
            typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
            if categoria is None:
                raise typer.Exit(code=2)
