from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from barnes.db.connection import get_connection
from barnes.db.export import (
    ExportError,
    list_trial_ids_by_phase,
    load_export_context,
    load_identity,
    set_experiment_group,
)
from barnes.metrics.latency import load_time_limit
from barnes.report import write_csv
from barnes.report.probes_csv import (
    PROBES_CSV_ALL_COLUMNS,
    build_probes_row,
    missing_probes_row,
)
from barnes.report.trials_csv import (
    TRIALS_CSV_ALL_COLUMNS,
    build_trials_row,
    missing_trials_row,
)


def register_report_commands(report_app: typer.Typer, command_errors: Callable) -> None:
    @report_app.command("set-group")
    def set_group(
        experiment_id: Annotated[int, typer.Option(help="Id do experimento.")],
        group: Annotated[str, typer.Option(help='Rótulo do grupo (ex.: "WT").')],
        dsn: Annotated[str | None, typer.Option(help="DSN; padrão BARNES_DATABASE_URL.")] = None,
    ) -> None:
        """Registra o grupo experimental usado na coluna `group` do trials.csv (US-25)."""
        with command_errors():
            with get_connection(dsn) as conn:
                set_experiment_group(conn, experiment_id, group)
            typer.echo(f"Experimento #{experiment_id}: grupo definido como {group!r}.")

    @report_app.command("trials")
    def export_trials(
        experiment_id: Annotated[int, typer.Option(help="Id do experimento.")],
        out: Annotated[Path, typer.Option(help="Diretório de saída.")] = Path("data/processed"),
        tempo_limite_s: Annotated[
            float | None, typer.Option(help="Tempo limite do trial; padrão: configs/default.yaml.")
        ] = None,
        config: Annotated[Path, typer.Option(help="YAML com trial.tempo_limite_s.")] = Path(
            "configs/default.yaml"
        ),
        dsn: Annotated[str | None, typer.Option(help="DSN; padrão BARNES_DATABASE_URL.")] = None,
    ) -> None:
        """Exporta trials.csv (acquisition/habituation) no esquema do laboratório (US-25)."""
        with command_errors():
            limite = tempo_limite_s if tempo_limite_s is not None else load_time_limit(config)
            rows = []
            pendencias = []
            with get_connection(dsn) as conn:
                trial_ids = [
                    trial_id
                    for phase in ("habituation", "acquisition")
                    for trial_id in list_trial_ids_by_phase(conn, experiment_id, phase)
                ]
                for trial_id in trial_ids:
                    try:
                        context = load_export_context(conn, trial_id)
                        row = build_trials_row(context, tempo_limite_s=limite)
                    except ExportError as exc:
                        pendencias.append({"trial_id": trial_id, "motivo": str(exc)})
                        row = missing_trials_row(load_identity(conn, trial_id))
                    rows.append((trial_id, row))

            out.mkdir(parents=True, exist_ok=True)
            for trial_id, row in rows:
                write_csv([row], out / f"trial_{trial_id}.csv", TRIALS_CSV_ALL_COLUMNS)
            write_csv([row for _, row in rows], out / "trials.csv", TRIALS_CSV_ALL_COLUMNS)

            typer.echo(f"{len(rows)} trial(s) exportado(s) em {out / 'trials.csv'}.")
            for pendencia in pendencias:
                typer.echo(
                    f"Pendência: trial #{pendencia['trial_id']}: {pendencia['motivo']}", err=True
                )
            if pendencias:
                raise typer.Exit(code=2)

    @report_app.command("probes")
    def export_probes(
        experiment_id: Annotated[int, typer.Option(help="Id do experimento.")],
        out: Annotated[Path, typer.Option(help="Diretório de saída.")] = Path("data/processed"),
        dsn: Annotated[str | None, typer.Option(help="DSN; padrão BARNES_DATABASE_URL.")] = None,
    ) -> None:
        """Exporta probes.csv no esquema do laboratório (US-25/US-26)."""
        with command_errors():
            rows = []
            pendencias = []
            with get_connection(dsn) as conn:
                trial_ids = list_trial_ids_by_phase(conn, experiment_id, "probe")
                for probe_number, trial_id in enumerate(trial_ids):
                    try:
                        context = load_export_context(conn, trial_id)
                        row = build_probes_row(context, probe_number=probe_number)
                    except ExportError as exc:
                        pendencias.append({"trial_id": trial_id, "motivo": str(exc)})
                        row = missing_probes_row(load_identity(conn, trial_id), probe_number=probe_number)
                    rows.append((trial_id, row))

            out.mkdir(parents=True, exist_ok=True)
            for trial_id, row in rows:
                write_csv([row], out / f"probe_{trial_id}.csv", PROBES_CSV_ALL_COLUMNS)
            write_csv([row for _, row in rows], out / "probes.csv", PROBES_CSV_ALL_COLUMNS)

            typer.echo(f"{len(rows)} probe(s) exportado(s) em {out / 'probes.csv'}.")
            for pendencia in pendencias:
                typer.echo(
                    f"Pendência: trial #{pendencia['trial_id']}: {pendencia['motivo']}", err=True
                )
            if pendencias:
                raise typer.Exit(code=2)
