"""Command line workflow for camera scale calibration and metric processing."""

from __future__ import annotations

import csv
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import psycopg
import typer

from barnes.db import CalibrationRepository
from barnes.io.calibration import (
    Segment,
    calibrate_orientation,
    positive_number,
    verify_distance,
)
from barnes.io.calibration_ui import CalibrationCancelled, collect_segments
from barnes.io.video import read_reference_frame
from barnes.metrics import process_trial, validate_frame_size

app = typer.Typer(help="Labirinto de Barnes: calibração e métricas.", no_args_is_help=True)
Database = Annotated[
    str,
    typer.Option(
        "--database",
        envvar="BARNES_DATABASE",
        help="DSN PostgreSQL ou arquivo SQLite. Também aceita BARNES_DATABASE.",
    ),
]
Orientation = Annotated[
    str, typer.Option("--orientation", help="Identificador da câmera e posição.")
]
Video = Annotated[Path, typer.Option("--video", help="Vídeo original do trial.")]
Frame = Annotated[int, typer.Option("--frame", min=0, help="Índice do quadro, começando em zero.")]
DEFAULT_DATABASE = "data/barnes.sqlite3"


@contextmanager
def _command_errors():
    try:
        yield
    except typer.Exit:
        raise
    except CalibrationCancelled as exc:
        typer.echo(f"Cancelado: {exc}", err=True)
        raise typer.Exit(code=130) from exc
    except (sqlite3.Error, psycopg.Error) as exc:
        # Do not print a connection string, which may contain the database password.
        typer.echo("Erro no banco de dados. Confira a configuração e a disponibilidade.", err=True)
        raise typer.Exit(code=1) from exc
    except (ValueError, RuntimeError, OSError) as exc:
        typer.echo(f"Erro: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _length(value: float | None, prompt: str) -> float:
    if value is None:
        value = typer.prompt(prompt, type=float)
    return positive_number(value, "Comprimento real em centímetros")


@app.command()
def calibrate(
    video: Video,
    orientation: Orientation,
    length_1_cm: Annotated[float | None, typer.Option("--length-1-cm")] = None,
    length_2_cm: Annotated[float | None, typer.Option("--length-2-cm")] = None,
    frame: Frame = 0,
    database: Database = DEFAULT_DATABASE,
) -> None:
    """Marcar dois segmentos, calcular e salvar uma nova versão da escala."""
    with _command_errors():
        if not orientation.strip():
            raise ValueError("Informe o identificador da orientação de câmera.")
        reference = read_reference_frame(video, frame)
        length_a = _length(length_1_cm, "Comprimento real do segmento 1 (cm)")
        length_b = _length(length_2_cm, "Comprimento real do segmento 2 (cm)")
        first, second = collect_segments(reference)
        with CalibrationRepository(database) as repository:
            calibration = calibrate_orientation(
                repository,
                orientation,
                [Segment(*first, length_a), Segment(*second, length_b)],
                reference_video=str(video.resolve()),
                reference_frame=frame,
                reference_size=(reference.shape[1], reference.shape[0]),
            )
        typer.echo(
            f"Escala salva: {calibration.result.cm_per_px:.10g} cm/px | "
            f"orientação={calibration.orientation_id} | versão={calibration.version} | "
            f"id={calibration.id}"
        )
        typer.echo(f"Divergência entre segmentos: {calibration.result.relative_disagreement:.4%}")
        if calibration.version > 1:
            typer.echo("Métricas das escalas anteriores foram invalidadas; histórico preservado.")
        typer.echo("Confira a exatidão em uma terceira distância com barnes verify-scale.")


@app.command("verify-scale")
def verify_scale(
    video: Video,
    orientation: Orientation,
    length_cm: Annotated[float | None, typer.Option("--length-cm")] = None,
    frame: Frame = 0,
    database: Database = DEFAULT_DATABASE,
) -> None:
    """Conferir a escala com uma terceira distância; aceita somente erro < 3%."""
    with _command_errors():
        with CalibrationRepository(database) as repository:
            calibration = repository.require_calibration(orientation)
            reference = read_reference_frame(video, frame)
            validate_frame_size(calibration, (reference.shape[1], reference.shape[0]))
            length = _length(length_cm, "Comprimento real da terceira distância (cm)")
            (points,) = collect_segments(
                reference, window_name="Barnes - verificacao independente", segment_count=1
            )
            verification = verify_distance(calibration.result, Segment(*points, length))
        typer.echo(
            f"Escala {calibration.id} (versão {calibration.version}): "
            f"medido={verification.measured_cm:.6g} cm | "
            f"real={verification.known_cm:.6g} cm | erro={verification.relative_error:.4%}"
        )
        if not verification.accepted:
            typer.echo("Reprovado: o erro deve ser < 3%. Confira a montagem e recalibre.", err=True)
            raise typer.Exit(code=1)
        typer.echo("Verificação aceita: erro < 3%.")


@app.command()
def scale(
    orientation: Orientation,
    history: Annotated[bool, typer.Option("--history", help="Incluir versões anteriores.")] = False,
    database: Database = DEFAULT_DATABASE,
) -> None:
    """Consultar a escala ativa ou todo o histórico de uma orientação."""
    with _command_errors():
        with CalibrationRepository(database) as repository:
            active = repository.require_calibration(orientation)
            calibrations = repository.list_calibrations(orientation) if history else [active]
        for calibration in calibrations:
            state = "ativa" if calibration.id == active.id else "substituída"
            typer.echo(
                f"versão={calibration.version} | {calibration.result.cm_per_px:.10g} cm/px | "
                f"{state} | id={calibration.id} | {calibration.created_at}"
            )


def _read_trajectory(path: Path) -> tuple[list[tuple[float, float]], list[float]]:
    points, times = [], []
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not {"x_px", "y_px", "time_s"}.issubset(reader.fieldnames or []):
            raise ValueError("O CSV da trajetória exige as colunas x_px,y_px,time_s.")
        for row in reader:
            try:
                points.append((float(row["x_px"]), float(row["y_px"])))
                times.append(float(row["time_s"]))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Valores inválidos na linha {reader.line_num} da trajetória."
                ) from exc
    return points, times


@app.command()
def process(
    video: Video,
    trajectory: Annotated[Path, typer.Option("--trajectory", help="CSV com x_px,y_px,time_s.")],
    trial: Annotated[str, typer.Option("--trial", help="Identificador do trial.")],
    orientation: Orientation,
    ideal_distance_px: Annotated[
        float | None,
        typer.Option(
            "--ideal-distance-px", help="Distância ideal em pixels para eficiência de rota."
        ),
    ] = None,
    database: Database = DEFAULT_DATABASE,
) -> None:
    """Calcular métricas de uma trajetória já extraída e registrar a escala usada."""
    with _command_errors():
        with CalibrationRepository(database) as repository:
            # Fail before decoding video or reading trajectory when the scale is missing.
            repository.require_calibration(orientation)
            reference = read_reference_frame(video)
            points, times = _read_trajectory(trajectory)
            execution = process_trial(
                repository,
                trial,
                orientation,
                points,
                times,
                frame_size=(reference.shape[1], reference.shape[0]),
                ideal_distance_px=ideal_distance_px,
            )
        typer.echo(json.dumps(asdict(execution), ensure_ascii=False, indent=2))


@app.command()
def executions(
    trial: Annotated[str | None, typer.Option("--trial", help="Filtrar pelo trial.")] = None,
    database: Database = DEFAULT_DATABASE,
) -> None:
    """Consultar resultados, escala usada e validade após recalibrações."""
    with _command_errors():
        with CalibrationRepository(database) as repository:
            rows = repository.list_executions(trial)
        typer.echo(json.dumps([asdict(row) for row in rows], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
