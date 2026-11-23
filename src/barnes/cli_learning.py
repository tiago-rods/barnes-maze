"""US-22: banco -> figuras, sem ler mídia ou recalcular métricas."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer

from barnes.db.connection import get_connection
from barnes.db.learning import load_learning_rows
from barnes.report.learning import export_learning


def register_learning_commands(app: typer.Typer, command_errors: Callable) -> None:
    @app.command("learning-curves")
    def learning_curves(
        experiment: Annotated[list[int] | None, typer.Option("--experiment", min=1)] = None,
        phase: str = "acquisition",
        event: str = "primary",
        out: Path = Path("data/reports/learning"),
        dsn: str | None = None,
    ) -> None:
        """Curvas por animal e grupo em PNG/PDF/SVG, somente a partir do banco (US-22)."""
        with command_errors():
            with get_connection(dsn) as conn:
                rows = load_learning_rows(conn, experiment_ids=experiment, phase=phase, event=event)
            destination = export_learning(rows, out / uuid4().hex, phase=phase, event=event)
            typer.echo(f"Curvas exportadas: {destination}")
            typer.echo(
                "Censurados, nao avaliados e obsoletos identificados; consulte manifest.json."
            )
