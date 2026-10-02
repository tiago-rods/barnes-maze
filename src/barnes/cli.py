"""Interface de linha de comando do projeto Barnes Maze."""

from __future__ import annotations

import csv
import json
import math
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import cv2
import numpy as np
import psycopg
import typer

from barnes.db.calibration import (
    CalibrationRequiredError,
    get_calibration,
    require_calibration,
    save_calibration,
    save_verification,
    validate_frame_size,
)
from barnes.db.connection import apply_migrations, get_connection
from barnes.db.maze_configs import get_maze_config, insert_maze_config
from barnes.db.trial_results import get_trial_result, list_trial_results, upsert_trial_result
from barnes.db.trials import insert_trial
from barnes.geometry.holes import MazeGeometry, generate_holes
from barnes.geometry.validation import GeometryValidationError
from barnes.io.calibration import (
    CalibrationResult,
    Segment,
    calculate_calibration,
    positive_number,
    verify_distance,
)
from barnes.io.calibration_ui import CalibrationCancelled, collect_segments
from barnes.io.video import VideoLoadError, VideoMetadata, load_trial_video, read_frame
from barnes.metrics import process_trial

app = typer.Typer()

db_app = typer.Typer(help="Comandos de banco de dados.")
app.add_typer(db_app, name="db")

video_app = typer.Typer(help="Comandos de vídeo.")
app.add_typer(video_app, name="video")

maze_app = typer.Typer(help="Comandos de geometria do labirinto.")
app.add_typer(maze_app, name="maze")

scale_app = typer.Typer(help="Calibração da escala px→cm por orientação de câmera (US-02).")
app.add_typer(scale_app, name="scale")

metrics_app = typer.Typer(help="Métricas calculadas com a escala calibrada (US-02).")
app.add_typer(metrics_app, name="metrics")


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
    """Desenha o círculo da plataforma, uma marca no centro e os buracos sobre uma cópia do quadro."""
    canvas = frame.copy()
    center = (int(geometry.center_x_px), int(geometry.center_y_px))
    cv2.circle(canvas, center, int(geometry.platform_radius_px), (0, 255, 0), 1)
    cv2.drawMarker(canvas, center, (0, 255, 255), cv2.MARKER_CROSS, 16, 2)
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


MAX_INTERACTIVE_HOLE_COUNT = 30

_INSTRUCTIONS = (
    "arraste = centro/raio/angulo | botao direito = marca alvo | "
    "a = auto-detectar plataforma | +/- = N (agora {n}, max 30) | Enter/q confirma"
)


def _detect_platform_circle(frame: np.ndarray) -> tuple[float, float, float] | None:
    """Estima centro e raio da plataforma a partir do quadro (threshold + contorno).

    Assume a plataforma como a maior região clara contígua do quadro — mesma
    técnica padrão de segmentação por limiar usada em `barnes.io.video`/
    tracking de vídeo em geral (Otsu escolhe o limiar automaticamente, sem
    número mágico fixo, já que a exposição varia entre gravações). Serve só
    como ponto de partida: o operador ainda pode corrigir arrastando o mouse.

    Returns:
        `(center_x_px, center_y_px, radius_px)`, ou `None` se nenhum contorno
        for encontrado.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Abertura morfológica: remove pontes finas onde um objeto externo (mão,
    # cabo) toca a borda da plataforma na segmentação. Sem isso, um contato
    # pequeno já distorce o círculo mínimo envolvente — não é um problema de
    # ângulo/rotação de câmera, é a mão do operador entrando no quadro.
    kernel_size = max(3, round(min(frame.shape[:2]) * 0.035) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    opened = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    (x, y), radius = cv2.minEnclosingCircle(largest)
    return float(x), float(y), float(radius)


def _try_generate_geometry(state: dict, hole_radius_px: float) -> MazeGeometry | None:
    """Gera a geometria a partir do estado do mouse/teclado, ou None se inválida."""
    center_x_px, center_y_px = state["center"]
    try:
        return generate_holes(
            center_x_px=center_x_px,
            center_y_px=center_y_px,
            platform_radius_px=state["radius"],
            hole_count=state["hole_count"],
            start_angle_deg=state["start_angle"],
            target_hole_number=state["target"],
            hole_radius_px=hole_radius_px,
        )
    except GeometryValidationError:
        return None


def _adjust_geometry_interactively(
    frame: np.ndarray,
    *,
    center_x_px: float,
    center_y_px: float,
    platform_radius_px: float,
    hole_count: int,
    start_angle_deg: float,
    target_hole_number: int,
    hole_radius_px: float,
) -> MazeGeometry:
    """Janela OpenCV para ajustar a geometria com o mouse (Cenário 1).

    Arrastar o botão esquerdo do centro real até um buraco visível define
    centro, raio e ângulo inicial de uma vez (o ângulo vem da direção do
    arraste). Clicar com o botão direito perto de um buraco já desenhado
    marca aquele buraco como alvo. Teclas '+'/'-' mudam N ao vivo. Tecla
    'q'/Esc/Enter confirma e fecha a janela, retornando a última geometria
    válida exibida — combinações inválidas (ex.: N <= 2 durante o ajuste)
    simplesmente não substituem essa última geometria válida.
    """
    window = "Ajuste da geometria - Barnes"
    cv2.namedWindow(window)

    state = {
        "center": (center_x_px, center_y_px),
        "radius": platform_radius_px,
        "start_angle": start_angle_deg,
        "hole_count": hole_count,
        "target": target_hole_number,
        "dragging": False,
    }

    def on_mouse(event: int, x: int, y: int, _flags: int, _param: object) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            state["dragging"] = True
            state["center"] = (float(x), float(y))
        elif event == cv2.EVENT_MOUSEMOVE and state["dragging"]:
            cx, cy = state["center"]
            state["radius"] = max(math.hypot(x - cx, y - cy), 1.0)
            state["start_angle"] = math.degrees(math.atan2(y - cy, x - cx)) % 360.0
        elif event == cv2.EVENT_LBUTTONUP:
            state["dragging"] = False
        elif event == cv2.EVENT_RBUTTONDOWN:
            candidate = _try_generate_geometry(state, hole_radius_px)
            if candidate is not None:
                nearest = min(
                    candidate.holes, key=lambda h: math.hypot(h.x_px - x, h.y_px - y)
                )
                if math.hypot(nearest.x_px - x, nearest.y_px - y) <= nearest.radius_px * 2:
                    state["target"] = nearest.hole_number

    cv2.setMouseCallback(window, on_mouse)

    geometry = _try_generate_geometry(state, hole_radius_px)
    while True:
        key = cv2.waitKey(30) & 0xFF
        if key in (ord("+"), ord("=")):
            state["hole_count"] = min(state["hole_count"] + 1, MAX_INTERACTIVE_HOLE_COUNT)
        elif key in (ord("-"), ord("_")):
            state["hole_count"] = max(state["hole_count"] - 1, 3)
        elif key == ord("a"):
            detected = _detect_platform_circle(frame)
            if detected is not None:
                center_x, center_y, radius = detected
                state["center"] = (center_x, center_y)
                state["radius"] = radius
        elif key in (13, ord("q"), 27):  # 13 = Enter, 27 = Esc
            break
        state["target"] = min(state["target"], state["hole_count"] - 1)

        candidate = _try_generate_geometry(state, hole_radius_px)
        if candidate is not None:
            geometry = candidate

        canvas = _draw_geometry_overlay(frame, geometry) if geometry is not None else frame.copy()
        cv2.putText(
            canvas,
            _INSTRUCTIONS.format(n=state["hole_count"]),
            (10, canvas.shape[0] - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 255),
            1,
        )
        cv2.imshow(window, canvas)

    cv2.destroyWindow(window)
    if geometry is None:
        raise GeometryValidationError(
            "platform_radius_px", "Nenhuma geometria válida foi definida na janela interativa."
        )
    return geometry


@maze_app.command("create")
def create_maze(
    experiment_id: int = typer.Option(..., help="Id do experimento ao qual esta montagem pertence."),
    name: str = typer.Option(..., help="Nome/rótulo da montagem (ex. 'setup padrão')."),
    reference_frame: str = typer.Option(
        ..., help="Caminho do vídeo/imagem de referência para o overlay."
    ),
    arena_diameter_cm: float = typer.Option(..., help="Diâmetro da arena, em cm."),
    hole_diameter_cm: float = typer.Option(..., help="Diâmetro de cada buraco, em cm."),
    center_x: float = typer.Option(
        None,
        help="Coordenada x do centro, em pixels. No modo interativo, padrão é o centro do "
        "quadro e pode ser refeito arrastando o mouse; obrigatório com --no-interactive.",
    ),
    center_y: float = typer.Option(None, help="Coordenada y do centro, em pixels (ver --center-x)."),
    platform_radius_px: float = typer.Option(
        None,
        help="Raio da circunferência dos buracos, em pixels. No modo interativo, padrão é "
        "uma estimativa a partir do quadro; obrigatório com --no-interactive.",
    ),
    hole_count: int = typer.Option(
        20, help="Número de buracos, N (> 2). Ajustável com +/- no modo interativo."
    ),
    start_angle_deg: float = typer.Option(0.0, help="Ângulo do buraco de índice 0, em graus."),
    target_hole_number: int = typer.Option(
        0, help="Índice do buraco-alvo, 0..N-1. Ajustável clicando com o botão direito."
    ),
    hole_radius_px: float = typer.Option(15.0, help="Raio de cada buraco, em pixels."),
    frame_index: int = typer.Option(0, help="Quadro do vídeo de referência usado no overlay."),
    interactive: bool = typer.Option(True, help="Abrir janela OpenCV para ajuste antes de confirmar."),
    dsn: str = typer.Option(None, help="DSN do Postgres. Padrão: BARNES_DATABASE_URL."),
) -> None:
    """Cria uma montagem: gera os buracos, mostra overlay e persiste (US-04)."""
    if not interactive and (center_x is None or center_y is None or platform_radius_px is None):
        typer.echo(
            "Erro: --center-x, --center-y e --platform-radius-px são obrigatórios com "
            "--no-interactive (no modo interativo eles têm padrão e são ajustados na janela).",
            err=True,
        )
        raise typer.Exit(code=1)

    if interactive:
        frame = read_frame(reference_frame, frame_index)
        height, width = frame.shape[:2]
        if center_x is None:
            center_x = width / 2
        if center_y is None:
            center_y = height / 2
        if platform_radius_px is None:
            platform_radius_px = min(width, height) * 0.35

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
        if not interactive:
            typer.echo(f"Erro no parâmetro '{exc.field}': {exc}", err=True)
            raise typer.Exit(code=1) from exc
        geometry = None  # o operador corrige arrastando o mouse na janela

    if interactive:
        geometry = _adjust_geometry_interactively(
            frame,
            center_x_px=center_x,
            center_y_px=center_y,
            platform_radius_px=platform_radius_px,
            hole_count=hole_count,
            start_angle_deg=start_angle_deg,
            target_hole_number=target_hole_number,
            hole_radius_px=hole_radius_px,
        )

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


# --- Calibração px→cm e métricas (US-02) --------------------------------------

Video = Annotated[Path, typer.Option("--video", help="Vídeo original do trial (.mp4).")]
Frame = Annotated[int, typer.Option("--frame", min=0, help="Índice do quadro, começando em zero.")]
MazeConfigId = Annotated[
    int, typer.Option("--maze-config-id", help="Id da montagem (maze_configs) a calibrar/usar.")
]


@contextmanager
def _command_errors():
    try:
        yield
    except typer.Exit:
        raise
    except CalibrationCancelled as exc:
        typer.echo(f"Cancelado: {exc}", err=True)
        raise typer.Exit(code=130) from exc
    except CalibrationRequiredError as exc:
        typer.echo(f"Erro: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except psycopg.Error as exc:
        # Do not print a connection string, which may contain the database password.
        typer.echo("Erro no banco de dados. Confira a configuração e a disponibilidade.", err=True)
        raise typer.Exit(code=1) from exc
    except (VideoLoadError, ValueError, RuntimeError, OSError) as exc:
        typer.echo(f"Erro: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _length(value: float | None, prompt: str) -> float:
    if value is None:
        value = typer.prompt(prompt, type=float)
    return positive_number(value, "Comprimento real em centímetros")


@scale_app.command("calibrate")
def calibrate(
    video: Video,
    maze_config_id: MazeConfigId,
    length_1_cm: Annotated[float | None, typer.Option("--length-1-cm")] = None,
    length_2_cm: Annotated[float | None, typer.Option("--length-2-cm")] = None,
    frame: Frame = 0,
    dsn: str = typer.Option(None, help="DSN do Postgres. Padrão: BARNES_DATABASE_URL."),
) -> None:
    """Marcar dois segmentos, calcular e salvar a escala da montagem (RN01/RN02/RN05)."""
    with _command_errors():
        with get_connection(dsn) as conn:
            # Valida que a montagem existe antes de abrir a janela e pedir os cliques.
            get_calibration(conn, maze_config_id)
        reference = read_frame(video, frame)
        length_a = _length(length_1_cm, "Comprimento real do segmento 1 (cm)")
        length_b = _length(length_2_cm, "Comprimento real do segmento 2 (cm)")
        first, second = collect_segments(reference)
        result = calculate_calibration([Segment(*first, length_a), Segment(*second, length_b)])
        with get_connection(dsn) as conn:
            save_calibration(
                conn,
                maze_config_id,
                result,
                reference_video=str(video.resolve()),
                reference_frame=frame,
                reference_size=(reference.shape[1], reference.shape[0]),
            )
        typer.echo(f"Escala salva: {result.cm_per_px:.10g} cm/px (montagem #{maze_config_id}).")
        typer.echo(f"Divergência entre segmentos: {result.relative_disagreement:.4%}")
        typer.echo(
            "Recalibrar sobrescreve a escala anterior da montagem; resultados já calculados "
            "com a escala anterior ficam marcados como obsoletos (barnes metrics executions)."
        )
        typer.echo("Confira a exatidão em uma terceira distância com barnes scale verify.")


@scale_app.command("verify")
def verify_scale(
    video: Video,
    maze_config_id: MazeConfigId,
    length_cm: Annotated[float | None, typer.Option("--length-cm")] = None,
    frame: Frame = 0,
    dsn: str = typer.Option(None, help="DSN do Postgres. Padrão: BARNES_DATABASE_URL."),
) -> None:
    """Conferir a escala com uma terceira distância; aceita somente erro < 3% (RN04)."""
    with _command_errors():
        reference = read_frame(video, frame)
        with get_connection(dsn) as conn:
            calibration = require_calibration(conn, maze_config_id)
        validate_frame_size(calibration, (reference.shape[1], reference.shape[0]))
        length = _length(length_cm, "Comprimento real da terceira distância (cm)")
        (points,) = collect_segments(
            reference, window_name="Barnes - verificacao independente", segment_count=1
        )
        # calculate_calibration() já validou segments/cm_per_px na calibração; os dois
        # campos abaixo não são usados por verify_distance, só o reuso de ponto e a escala.
        reconstructed = CalibrationResult(
            segments=calibration.segments,
            cm_per_px=calibration.cm_per_px,
            relative_disagreement=0.0,
            angle_degrees=0.0,
        )
        verification = verify_distance(reconstructed, Segment(*points, length))
        with get_connection(dsn) as conn:
            save_verification(conn, maze_config_id, verification.relative_error)
        typer.echo(
            f"Montagem #{maze_config_id}: medido={verification.measured_cm:.6g} cm | "
            f"real={verification.known_cm:.6g} cm | erro={verification.relative_error:.4%}"
        )
        if not verification.accepted:
            typer.echo("Reprovado: o erro deve ser < 3%. Confira a montagem e recalibre.", err=True)
            raise typer.Exit(code=1)
        typer.echo("Verificação aceita: erro < 3%.")


@scale_app.command("show")
def show_scale(
    maze_config_id: MazeConfigId,
    dsn: str = typer.Option(None, help="DSN do Postgres. Padrão: BARNES_DATABASE_URL."),
) -> None:
    """Consultar a escala atual da montagem."""
    with _command_errors():
        with get_connection(dsn) as conn:
            calibration = require_calibration(conn, maze_config_id)
        typer.echo(
            f"{calibration.cm_per_px:.10g} cm/px | calibrada em {calibration.calibration_date}"
        )
        if calibration.measured_error_pct is not None:
            typer.echo(f"Última verificação independente: erro={calibration.measured_error_pct:.4g}%")
        else:
            typer.echo("Ainda sem verificação independente (barnes scale verify).")


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


@metrics_app.command("process")
def process(
    video: Video,
    trajectory: Annotated[Path, typer.Option("--trajectory", help="CSV com x_px,y_px,time_s.")],
    trial: Annotated[int, typer.Option("--trial", help="Id do trial (trials.id).")],
    maze_config_id: MazeConfigId,
    frame: Frame = 0,
    ideal_distance_px: Annotated[
        float | None,
        typer.Option(
            "--ideal-distance-px", help="Distância ideal em pixels para eficiência de rota."
        ),
    ] = None,
    dsn: str = typer.Option(None, help="DSN do Postgres. Padrão: BARNES_DATABASE_URL."),
) -> None:
    """Calcular métricas de uma trajetória já extraída e registrar a escala usada (RN03/RN05)."""
    with _command_errors():
        reference = read_frame(video, frame)
        with get_connection(dsn) as conn:
            calibration = require_calibration(conn, maze_config_id)
            # Falha na resolução antes de ler o CSV da trajetória inteiro.
            validate_frame_size(calibration, (reference.shape[1], reference.shape[0]))
            points, times = _read_trajectory(trajectory)
            metrics = process_trial(
                calibration.cm_per_px,
                points,
                times,
                frame_size=(reference.shape[1], reference.shape[0]),
                ideal_distance_px=ideal_distance_px,
            )
            upsert_trial_result(
                conn,
                trial,
                distance_cm=metrics["distance_cm"],
                speed_mean_cm=metrics["mean_speed_cm_s"],
                route_efficiency=metrics.get("route_efficiency"),
                px_per_10cm_used=10 / calibration.cm_per_px,
                calculated_at=datetime.now(UTC),
            )
        typer.echo(json.dumps(metrics, ensure_ascii=False, indent=2))


@metrics_app.command("executions")
def executions(
    trial: Annotated[int | None, typer.Option("--trial", help="Filtrar por id do trial.")] = None,
    dsn: str = typer.Option(None, help="DSN do Postgres. Padrão: BARNES_DATABASE_URL."),
) -> None:
    """Consultar resultados calculados e se ficaram obsoletos após recalibração (RN05)."""
    with _command_errors():
        with get_connection(dsn) as conn:
            if trial is not None:
                result = get_trial_result(conn, trial)
                rows = [] if result is None else [result]
            else:
                rows = list_trial_results(conn)
        typer.echo(json.dumps([asdict(row) for row in rows], ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    app()
