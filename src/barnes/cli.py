"""Interface de linha de comando do projeto Barnes Maze."""

from __future__ import annotations

from pathlib import Path

import cv2
import typer

from barnes.db.connection import apply_migrations, get_connection
from barnes.db.trials import insert_trial
from barnes.io.video import VideoLoadError, VideoMetadata, load_trial_video, read_frame

app = typer.Typer()

db_app = typer.Typer(help="Comandos de banco de dados.")
app.add_typer(db_app, name="db")

video_app = typer.Typer(help="Comandos de vídeo.")
app.add_typer(video_app, name="video")


@db_app.command("migrate")
def migrate(
    dsn: str = typer.Option(
        None, help="DSN do Postgres. Padrão: variável de ambiente BARNES_DATABASE_URL."
    ),
) -> None:
    """Aplica as migrações pendentes em database/migrations/."""
    with get_connection(dsn) as conn:
        applied = apply_migrations(conn)

    if applied:
        typer.echo(f"Migrações aplicadas: {', '.join(applied)}")
    else:
        typer.echo("Nenhuma migração pendente.")


def _print_metadata(video: VideoMetadata) -> None:
    typer.echo(f"Arquivo: {video.path}")
    typer.echo(f"Resolução: {video.width}x{video.height}")
    typer.echo(f"Quadros: {video.frame_count}")
    typer.echo(f"Duração: {video.duration_s:.2f}s")
    typer.echo(f"fps declarado (cabeçalho): {video.fps_declared:.3f}")
    typer.echo(f"fps real (medido): {video.fps_real:.3f}")
    if video.fps_is_variable:
        typer.echo("AVISO: fps variável detectado — usando fps medido pelos carimbos de tempo.")
    typer.echo(f"Hash (sha256): {video.content_hash}")


def _interactive_preview(path: Path, start_index: int) -> None:
    """Abre uma janela navegável entre quadros: n/d = próximo, p/a = anterior, q/Esc = sair."""
    frame_index = start_index
    window = f"Preview - {path.name}"
    while True:
        try:
            frame = read_frame(path, frame_index)
        except VideoLoadError:
            typer.echo(f"Quadro {frame_index} indisponível.")
            frame_index = max(frame_index - 1, 0)
            continue

        cv2.imshow(window, frame)
        cv2.setWindowTitle(window, f"{path.name} — quadro {frame_index}")
        key = cv2.waitKey(0) & 0xFF
        if key in (ord("q"), 27):  # 27 = Esc
            break
        elif key in (ord("n"), ord("d")):
            frame_index += 1
        elif key in (ord("p"), ord("a")):
            frame_index = max(frame_index - 1, 0)
    cv2.destroyWindow(window)


@video_app.command("load")
def load_video(
    path: str = typer.Argument(..., help="Caminho do arquivo .mp4 do trial."),
    experiment_id: int = typer.Option(
        None, help="Id do experimento — se informado (junto com --maze-config-id), persiste o trial."
    ),
    maze_config_id: int = typer.Option(None, help="Id da configuração de labirinto do trial."),
    phase: str = typer.Option("acquisition", help="habituation | acquisition | probe"),
    day: int = typer.Option(1, help="Número do dia do trial dentro do experimento."),
    trial_in_day: int = typer.Option(1, help="Ordem do trial dentro do dia."),
    frame_index: int = typer.Option(0, help="Quadro inicial da pré-visualização."),
    preview: bool = typer.Option(True, help="Abrir janela de pré-visualização navegável."),
    dsn: str = typer.Option(None, help="DSN do Postgres. Padrão: BARNES_DATABASE_URL."),
) -> None:
    """Carrega um vídeo de trial, mostra os metadados e, se pedido, persiste (US-01)."""
    try:
        video = load_trial_video(path)
    except VideoLoadError as exc:
        typer.echo(f"Erro: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_metadata(video)

    if experiment_id is not None and maze_config_id is not None:
        with get_connection(dsn) as conn:
            trial_id = insert_trial(
                conn,
                experiment_id=experiment_id,
                maze_config_id=maze_config_id,
                video=video,
                phase=phase,
                day_number=day,
                trial_number_in_day=trial_in_day,
            )
        typer.echo(f"Trial #{trial_id} salvo no banco.")

    if preview:
        _interactive_preview(video.path, frame_index)


if __name__ == "__main__":
    app()
