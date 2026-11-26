"""US-23: banco -> tabela de contingência e teste de independência, sem vídeo."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer

from barnes.db.connection import get_connection
from barnes.db.contingency import load_strategy_rows
from barnes.stats.contingency import (
    DEFAULT_STRATEGIES,
    StatsConfigError,
    StrategyObservation,
    build_contingency_table,
    load_min_expected_frequency,
    render_markdown,
    run_independence_test,
)

_DIMENSIONS = ("sessao", "grupo")


def _observations(rows: list[dict], dimensao: str) -> list[StrategyObservation]:
    if dimensao == "sessao":
        return [StrategyObservation(linha=row["session"], estrategia=row["search_strategy"]) for row in rows]
    sem_grupo = [row["trial_id"] for row in rows if row["grupo"] is None]
    if sem_grupo:
        raise ValueError(
            f"Trial(s) sem grupo experimental definido: {sem_grupo}. Rode "
            "`barnes report set-group` (US-25) antes de usar --dimensao grupo."
        )
    return [StrategyObservation(linha=row["grupo"], estrategia=row["search_strategy"]) for row in rows]


def register_stats_commands(stats_app: typer.Typer, command_errors: Callable) -> None:
    @stats_app.command("contingency")
    def contingency(
        experiment_id: Annotated[int, typer.Option(help="Id do experimento.")],
        dimensao: Annotated[
            str,
            typer.Option(
                help="'sessao' (trials.day_number) ou 'grupo' (experiments.group_label, RN04)."
            ),
        ] = "sessao",
        phase: Annotated[str, typer.Option(help="Fase dos trials considerados.")] = "acquisition",
        config: Annotated[
            Path, typer.Option(help="YAML com estatistica.frequencia_esperada_minima.")
        ] = Path("configs/default.yaml"),
        out: Annotated[
            Path, typer.Option(help="Diretório das rodadas.")
        ] = Path("data/reports/contingency"),
        dsn: Annotated[str | None, typer.Option(help="DSN; padrão BARNES_DATABASE_URL.")] = None,
    ) -> None:
        """Tabela sessão/grupo × estratégia (US-20) e qui-quadrado/Fisher (US-23)."""
        with command_errors():
            if dimensao not in _DIMENSIONS:
                raise ValueError(f"dimensao deve ser uma de {_DIMENSIONS}.")
            with get_connection(dsn) as conn:
                rows = load_strategy_rows(conn, experiment_id, phase=phase)
            observations = _observations(rows, dimensao)
            tabela = build_contingency_table(
                observations, categorias=DEFAULT_STRATEGIES, dimensao=dimensao
            )

            destination = out / uuid4().hex
            destination.mkdir(parents=True, exist_ok=True)

            try:
                limiar = load_min_expected_frequency(config)
            except StatsConfigError as exc:
                json_path = destination / "tabela.json"
                json_path.write_text(
                    json.dumps(tabela.as_record(), ensure_ascii=False, indent=2), encoding="utf-8"
                )
                typer.echo(f"Tabela gerada, sem teste de independência: {exc}")
                typer.echo(f"Tabela: {json_path}")
                raise typer.Exit(code=2) from exc

            resultado = run_independence_test(tabela, frequencia_esperada_minima=limiar)
            record = resultado.as_record() | {
                "experiment_id": experiment_id,
                "phase": phase,
                "criado_em": datetime.now(UTC).isoformat(),
            }
            json_path = destination / "resultado.json"
            md_path = destination / "resultado.md"
            json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            md_path.write_text(render_markdown(resultado), encoding="utf-8")

            typer.echo(render_markdown(resultado))
            typer.echo(f"Registro: {json_path}")
