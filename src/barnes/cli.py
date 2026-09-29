"""Interface de linha de comando do projeto Barnes Maze."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import typer

from barnes.db.connection import apply_migrations, get_connection
from barnes.db.maze_configs import get_maze_config, insert_maze_config
from barnes.db.trials import insert_trial
from barnes.geometry.holes import MazeGeometry, generate_holes
from barnes.geometry.validation import GeometryValidationError
from barnes.io.video import VideoLoadError, VideoMetadata, load_trial_video, read_frame

app = typer.Typer()

db_app = typer.Typer(help="Comandos de banco de dados.")
app.add_typer(db_app, name="db")

video_app = typer.Typer(help="Comandos de vídeo.")
app.add_typer(video_app, name="video")

maze_app = typer.Typer(help="Comandos de geometria do labirinto.")
app.add_typer(maze_app, name="maze")


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


def _draw_geometry_overlay(frame: np.ndarray, geometry: MazeGeometry) -> np.ndarray:
    """Desenha o círculo da plataforma e os buracos sobre uma cópia do quadro."""
    canvas = frame.copy()
    cv2.circle(
        canvas,
        (int(geometry.center_x_px), int(geometry.center_y_px)),
        int(geometry.platform_radius_px),
        (0, 255, 0),
        1,
    )
    for hole in geometry.holes:
        color = (0, 0, 255) if hole.is_target else (255, 0, 0)
        cv2.circle(canvas, (int(hole.x_px), int(hole.y_px)), max(int(hole.radius_px), 1), color, -1)
        cv2.putText(
            canvas,
            str(hole.hole_number),
            (int(hole.x_px) + 5, int(hole.y_px) - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (255, 255, 255),
            1,
        )
    return canvas


def _adjust_geometry_interactively(frame: np.ndarray, initial: MazeGeometry) -> MazeGeometry:
    """Janela OpenCV com trackbars para ajustar centro/raio/N/ângulo/alvo (Cenário 1).

    Tecla 'q'/Esc/Enter confirma e fecha a janela, retornando a última
    geometria válida exibida. Combinações de trackbar que violam
    validate_parameters mantêm a última geometria válida no lugar de
    quebrar o preview.
    """
    window = "Ajuste da geometria - Barnes"
    cv2.namedWindow(window)
    height, width = frame.shape[:2]
    cv2.createTrackbar("center_x", window, int(initial.center_x_px), width, lambda v: None)
    cv2.createTrackbar("center_y", window, int(initial.center_y_px), height, lambda v: None)
    cv2.createTrackbar(
        "radius", window, int(initial.platform_radius_px), max(width, height), lambda v: None
    )
    cv2.createTrackbar("N", window, initial.hole_count, 48, lambda v: None)
    cv2.createTrackbar("angle_start", window, 0, 359, lambda v: None)
    cv2.createTrackbar(
        "target", window, initial.target_hole.hole_number, initial.hole_count - 1, lambda v: None
    )

    geometry = initial
    while True:
        hole_count = max(cv2.getTrackbarPos("N", window), 1)
        target = min(cv2.getTrackbarPos("target", window), hole_count - 1)
        try:
            geometry = generate_holes(
                center_x_px=cv2.getTrackbarPos("center_x", window),
                center_y_px=cv2.getTrackbarPos("center_y", window),
                platform_radius_px=cv2.getTrackbarPos("radius", window),
                hole_count=hole_count,
                start_angle_deg=cv2.getTrackbarPos("angle_start", window),
                target_hole_number=target,
                hole_radius_px=geometry.holes[0].radius_px,
            )
        except GeometryValidationError:
            pass  # mantém a última geometria válida (ex.: N<=2 durante o arraste do trackbar)
        cv2.imshow(window, _draw_geometry_overlay(frame, geometry))
        key = cv2.waitKey(30) & 0xFF
        if key in (ord("q"), 13, 27):  # 13 = Enter, 27 = Esc
            break
    cv2.destroyWindow(window)
    return geometry


@maze_app.command("create")
def create_maze(
    experiment_id: int = typer.Option(..., help="Id do experimento ao qual esta montagem pertence."),
    name: str = typer.Option(..., help="Nome/rótulo da montagem (ex. 'setup padrão')."),
    reference_frame: str = typer.Option(
        ..., help="Caminho do vídeo/imagem de referência para o overlay."
    ),
    center_x: float = typer.Option(..., help="Coordenada x do centro da plataforma, em pixels."),
    center_y: float = typer.Option(..., help="Coordenada y do centro da plataforma, em pixels."),
    platform_radius_px: float = typer.Option(
        ..., help="Raio da circunferência dos buracos, em pixels."
    ),
    hole_count: int = typer.Option(..., help="Número de buracos, N (> 2)."),
    start_angle_deg: float = typer.Option(..., help="Ângulo do buraco de índice 0, em graus."),
    target_hole_number: int = typer.Option(..., help="Índice do buraco-alvo, 0..N-1."),
    hole_radius_px: float = typer.Option(..., help="Raio de cada buraco, em pixels."),
    arena_diameter_cm: float = typer.Option(..., help="Diâmetro da arena, em cm."),
    hole_diameter_cm: float = typer.Option(..., help="Diâmetro de cada buraco, em cm."),
    frame_index: int = typer.Option(0, help="Quadro do vídeo de referência usado no overlay."),
    interactive: bool = typer.Option(True, help="Abrir janela OpenCV para ajuste antes de confirmar."),
    dsn: str = typer.Option(None, help="DSN do Postgres. Padrão: BARNES_DATABASE_URL."),
) -> None:
    """Cria uma montagem: gera os buracos, mostra overlay e persiste (US-04)."""
    try:
        geometry = generate_holes(
            center_x_px=center_x,
            center_y_px=center_y,
            platform_radius_px=platform_radius_px,
            hole_count=hole_count,
            start_angle_deg=start_angle_deg,
            target_hole_number=target_hole_number,
            hole_radius_px=hole_radius_px,
        )
    except GeometryValidationError as exc:
        typer.echo(f"Erro no parâmetro '{exc.field}': {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if interactive:
        frame = read_frame(reference_frame, frame_index)
        geometry = _adjust_geometry_interactively(frame, geometry)

    with get_connection(dsn) as conn:
        maze_config_id = insert_maze_config(
            conn,
            experiment_id=experiment_id,
            name=name,
            arena_diameter_cm=arena_diameter_cm,
            hole_diameter_cm=hole_diameter_cm,
            geometry=geometry,
        )
    typer.echo(f"Montagem #{maze_config_id} salva no banco ({geometry.hole_count} buracos).")


@maze_app.command("show")
def show_maze(
    maze_config_id: int = typer.Argument(..., help="Id da configuração de labirinto a carregar."),
    dsn: str = typer.Option(None, help="DSN do Postgres. Padrão: BARNES_DATABASE_URL."),
) -> None:
    """Carrega uma montagem do banco e imprime sua geometria, sem interação (RN05)."""
    with get_connection(dsn) as conn:
        geometry = get_maze_config(conn, maze_config_id)

    typer.echo(f"Centro: ({geometry.center_x_px}, {geometry.center_y_px}) px")
    typer.echo(f"Raio da plataforma: {geometry.platform_radius_px} px")
    typer.echo(f"N buracos: {geometry.hole_count}")
    typer.echo(f"Alvo: buraco #{geometry.target_hole.hole_number}")
    for hole in geometry.holes:
        marker = " (ALVO)" if hole.is_target else ""
        typer.echo(
            f"  #{hole.hole_number}: angulo={hole.angle_deg:.1f} "
            f"pos=({hole.x_px:.1f}, {hole.y_px:.1f}){marker}"
        )


if __name__ == "__main__":
    app()
