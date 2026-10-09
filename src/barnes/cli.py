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

from barnes.cli_pose import register_pose_commands
from barnes.db.calibration import (
    CalibrationRequiredError,
    get_calibration,
    require_calibration,
    save_calibration,
    save_verification,
    validate_frame_size,
)
from barnes.db.catalog import list_catalog
from barnes.db.connection import DatabaseConfigError, apply_migrations, get_connection
from barnes.db.executions import get_execution, record_processing_execution
from barnes.db.maze_configs import get_maze_config, insert_maze_config
from barnes.db.trial_results import (
    get_trial_result,
    insert_trial_result,
    list_trial_result_history,
    list_trial_results,
)
from barnes.db.trials import (
    get_trial,
    get_trial_maze_config_id,
    get_trial_rotations,
    insert_trial,
    set_trajectory_path,
    set_trial_rotation,
)
from barnes.geometry.holes import Hole, MazeGeometry, generate_holes
from barnes.geometry.reference_frame import (
    ReferenceFrame,
    hole_to_room_angle,
    require_rotations,
    target_hole_for_trial,
)
from barnes.geometry.validation import GeometryValidationError
from barnes.io.calibration import (
    CalibrationResult,
    Segment,
    calculate_calibration,
    positive_number,
    verify_distance,
)
from barnes.io.calibration_ui import CalibrationCancelled, collect_segments
from barnes.io.trim import TrialInterval, TrialIntervalError, build_trial_interval
from barnes.io.video import (
    FileStatus,
    VideoLoadError,
    VideoMetadata,
    load_trial_video,
    read_frame,
    verify_video_file,
)
from barnes.metrics import process_trial
from barnes.pose.annotations import (
    ANNOTATIONS_CSV,
    from_slp,
    read_annotations_csv,
    validate_complete,
    write_annotations_csv,
)
from barnes.pose.dataset import file_sha256, git_revision_record
from barnes.pose.inference import INFERENCE_RECORD_KIND, load_inference_record
from barnes.pose.protocol import DEFAULT_CONFIG_PATH, load_annotation_protocol
from barnes.pose.report import count_by_region, empty_regions, resolve_maze_configs
from barnes.pose.sampling import (
    check_previous_export,
    export_frames,
    read_sampled_maze_config,
    sample_frames,
)
from barnes.pose.series import build_series, read_pose_csv
from barnes.pose.split import (
    SPLIT_CSV,
    build_manifest,
    check_no_leakage,
    read_manifest,
    split_by_trial,
    summarize,
    write_manifest,
)
from barnes.pose.trajectory import trajectory_path, write_trajectory
from barnes.provenance import PACKAGE_DIR, GitState, thresholds_snapshot

app = typer.Typer()

db_app = typer.Typer(help="Comandos de banco de dados.")
app.add_typer(db_app, name="db")

video_app = typer.Typer(help="Comandos de vídeo.")
app.add_typer(video_app, name="video")

trial_app = typer.Typer(help="Comandos de trial: rotação e referencial da sala (US-05).")
app.add_typer(trial_app, name="trial")

maze_app = typer.Typer(help="Comandos de geometria do labirinto.")
app.add_typer(maze_app, name="maze")

scale_app = typer.Typer(help="Calibração da escala px→cm por orientação de câmera (US-02).")
app.add_typer(scale_app, name="scale")

metrics_app = typer.Typer(help="Métricas calculadas com a escala calibrada (US-02).")
app.add_typer(metrics_app, name="metrics")

execution_app = typer.Typer(help="Proveniência das execuções registradas (US-27).")
app.add_typer(execution_app, name="execution")

catalog_app = typer.Typer(help="Catálogo de trials processados (US-27).")
app.add_typer(catalog_app, name="catalog")

pose_app = typer.Typer(help="Anotação, treino, avaliação e inferência local de pose (US-06/07/08).")
app.add_typer(pose_app, name="pose")


@db_app.command("migrate")
def migrate(
    dsn: str = typer.Option(
        None, help="DSN do Postgres. Padrão: variável de ambiente BARNES_DATABASE_URL."
    ),
) -> None:
    """Aplica as migrações pendentes em database/migrations/."""
    with _command_errors(), get_connection(dsn) as conn:
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


def _print_interval(interval: TrialInterval) -> None:
    origin = "ajustado manualmente" if interval.manually_adjusted else "detecção automática"
    typer.echo(
        f"Intervalo útil: {interval.start_s:.2f}s (quadro {interval.start_frame}) a "
        f"{interval.end_s:.2f}s (quadro {interval.end_frame}) — {origin}."
    )


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


TRIAL_PHASES = ("habituation", "acquisition", "probe")  # mesmo CHECK de trials.phase


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
    rotation_deg: float = typer.Option(
        0.0,
        help="Rotação da plataforma no trial, em graus (US-05). Padrão 0 porque o LNBio "
        "não rotaciona a plataforma (resposta B4, RN04); o valor é gravado explicitamente.",
    ),
    start_s: float = typer.Option(
        None,
        help="Início do intervalo útil, em segundos (US-03). Omitido: detecção automática "
        "da soltura. Informar sobrescreve a detecção e marca o intervalo como ajustado "
        "manualmente — não combinar com --start-frame.",
    ),
    end_s: float = typer.Option(
        None,
        help="Fim do intervalo útil, em segundos (US-03). Omitido: fim do vídeo — não "
        "combinar com --end-frame.",
    ),
    start_frame: int = typer.Option(
        None, help="Início do intervalo útil, em número de quadro — alternativa a --start-s."
    ),
    end_frame: int = typer.Option(
        None, help="Fim do intervalo útil, em número de quadro — alternativa a --end-s."
    ),
    frame_index: int = typer.Option(0, help="Quadro inicial da pré-visualização."),
    preview: bool = typer.Option(True, help="Abrir janela de pré-visualização navegável."),
    dsn: str = typer.Option(None, help="DSN do Postgres. Padrão: BARNES_DATABASE_URL."),
) -> None:
    """Carrega um vídeo de trial, mostra os metadados e, se pedido, persiste (US-01, US-03, US-05)."""
    with _command_errors():
        # Falhas de uso antes de ler o vídeo inteiro (Cenário 3: nada parcial no banco).
        persist = experiment_id is not None or maze_config_id is not None
        if persist and (experiment_id is None or maze_config_id is None):
            raise ValueError(
                "Para salvar o trial, informe --experiment-id e --maze-config-id juntos "
                "(sem os dois, o vídeo só é inspecionado, nada é salvo)."
            )
        if persist and phase not in TRIAL_PHASES:
            raise ValueError(f"--phase deve ser um de: {', '.join(TRIAL_PHASES)} (recebido {phase}).")

        video = load_trial_video(path)
        _print_metadata(video)

        try:
            interval = build_trial_interval(
                video, start_s=start_s, end_s=end_s, start_frame=start_frame, end_frame=end_frame
            )
        except TrialIntervalError as exc:
            typer.echo(f"Erro no intervalo útil: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        _print_interval(interval)

        if persist:
            try:
                with get_connection(dsn) as conn:
                    trial_id = insert_trial(
                        conn,
                        experiment_id=experiment_id,
                        maze_config_id=maze_config_id,
                        video=video,
                        phase=phase,
                        day_number=day,
                        trial_number_in_day=trial_in_day,
                        rotation_deg=rotation_deg,
                        interval=interval,
                    )
            except psycopg.errors.UniqueViolation as exc:
                # trials.content_hash é UNIQUE: o trial é identificado pelo conteúdo (RN05).
                raise ValueError(
                    f"Este vídeo já foi carregado como trial (mesmo conteúdo, hash "
                    f"{video.content_hash[:12]}…), possivelmente com outro nome de arquivo."
                ) from exc
            except psycopg.errors.ForeignKeyViolation as exc:
                raise ValueError(
                    f"Experimento #{experiment_id} ou montagem #{maze_config_id} não existe."
                ) from exc
            typer.echo(
                f"Trial #{trial_id} salvo no banco (rotação da plataforma: {rotation_deg % 360:g}°)."
            )

    if preview:
        _interactive_preview(video.path, frame_index)


@trial_app.command("set-rotation")
def set_rotation(
    trial_id: int = typer.Argument(..., help="Id do trial."),
    rotation_deg: float = typer.Argument(
        ..., help="Rotação da plataforma, em graus (para negativos, use `--` antes do valor)."
    ),
    dsn: str = typer.Option(None, help="DSN do Postgres. Padrão: BARNES_DATABASE_URL."),
) -> None:
    """Registra ou corrige a rotação da plataforma de um trial já carregado (US-05 RN01)."""
    with _command_errors(), get_connection(dsn) as conn:
        set_trial_rotation(conn, trial_id, rotation_deg)

    typer.echo(f"Trial #{trial_id}: rotação da plataforma registrada em {rotation_deg % 360:g}°.")


@trial_app.command("show")
def show_trial(
    trial_id: int = typer.Argument(..., help="Id do trial."),
    dsn: str = typer.Option(None, help="DSN do Postgres. Padrão: BARNES_DATABASE_URL."),
) -> None:
    """Mostra o buraco-alvo do trial nos referenciais da plataforma e da sala (US-05).

    Recusa o trial sem rotação registrada em vez de assumir 0° (Cenário 3).
    """
    with _command_errors(), get_connection(dsn) as conn:
        rotation_deg = require_rotations(get_trial_rotations(conn, [trial_id]))[trial_id]
        maze_config_id = get_trial_maze_config_id(conn, trial_id)
        geometry = get_maze_config(conn, maze_config_id)

    target_hole = target_hole_for_trial(geometry, rotation_deg=rotation_deg)
    target_angle = hole_to_room_angle(geometry, target_hole, rotation_deg=rotation_deg)

    # RN05: cada valor identifica o referencial em que está expresso.
    typer.echo(f"Trial #{trial_id} (montagem #{maze_config_id})")
    typer.echo(f"Rotação da plataforma: {rotation_deg:g}°")
    typer.echo(
        f"Alvo [plataforma] {ReferenceFrame.PLATFORM.column('target_hole')}: buraco #{target_hole}"
    )
    typer.echo(f"Alvo [sala] {ReferenceFrame.ROOM.column('target_angle_deg')}: {target_angle:.1f}°")


REFERENCE_HOLE_COLOR = (255, 0, 255)  # BGR magenta: buraco 0 = referência física (US-05)


def _draw_geometry_overlay(frame: np.ndarray, geometry: MazeGeometry) -> np.ndarray:
    """Desenha o círculo da plataforma, uma marca no centro e os buracos sobre uma cópia do quadro.

    O buraco 0 ganha um anel, uma linha a partir do centro e o rótulo "ref":
    ele precisa coincidir com o buraco físico de referência combinado com o
    laboratório, que ancora o referencial da sala (US-05).
    """
    canvas = frame.copy()
    center = (int(geometry.center_x_px), int(geometry.center_y_px))
    cv2.circle(canvas, center, int(geometry.platform_radius_px), (0, 255, 0), 1)
    cv2.drawMarker(canvas, center, (0, 255, 255), cv2.MARKER_CROSS, 16, 2)

    reference = geometry.holes[0]
    reference_center = (int(reference.x_px), int(reference.y_px))
    cv2.line(canvas, center, reference_center, REFERENCE_HOLE_COLOR, 1)
    cv2.circle(
        canvas, reference_center, max(int(reference.radius_px), 1) + 4, REFERENCE_HOLE_COLOR, 2
    )
    # Rótulo para fora da plataforma, na direção radial, longe do número "0".
    label_distance = geometry.platform_radius_px + reference.radius_px + 22
    label_angle = math.radians(reference.angle_deg)
    cv2.putText(
        canvas,
        "ref",
        (
            int(geometry.center_x_px + label_distance * math.cos(label_angle)) - 12,
            int(geometry.center_y_px + label_distance * math.sin(label_angle)) + 5,
        ),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        REFERENCE_HOLE_COLOR,
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


MAX_INTERACTIVE_HOLE_COUNT = 30
# Passo do ajuste do raio do buraco com '['/']'. Meio pixel: o raio é gravado
# como DOUBLE PRECISION (migração 0005), e num vídeo em que o buraco tem ~8 px
# de raio um passo de 1 px já seria ~12% do raio.
HOLE_RADIUS_STEP_PX = 0.5
MIN_HOLE_RADIUS_PX = 1.0

# Uma instrução por linha: juntas, não cabem num quadro de 640 px. Sem acentos
# porque as fontes Hershey do OpenCV não os desenham.
_INSTRUCTIONS = (
    "arraste do centro ate o buraco de REFERENCIA fisica (vira o buraco 0 / ref)",
    "botao direito = marca alvo | a = detectar BORDA | h = detectar BURACOS",
    "+/- = N (agora {n}, max 30) | [ ] = raio do buraco ({r:.1f} px) | Enter/q confirma",
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


def _fit_circle_to_points(points: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Círculo de mínimos quadrados (método algébrico de Kása) por um conjunto de pontos."""
    xs = np.array([p[0] for p in points], dtype=np.float64)
    ys = np.array([p[1] for p in points], dtype=np.float64)
    design = np.column_stack((2 * xs, 2 * ys, np.ones_like(xs)))
    target = xs**2 + ys**2
    (center_x, center_y, c), *_ = np.linalg.lstsq(design, target, rcond=None)
    radius = math.sqrt(max(c + center_x**2 + center_y**2, 0.0))
    return float(center_x), float(center_y), float(radius)


def _detect_hole_candidates(
    frame: np.ndarray, expected_hole_area_fraction: float
) -> list[tuple[float, float]]:
    """Localiza os centros das regiões escuras e aproximadamente circulares da plataforma.

    São os candidatos a buraco: dentro do disco da plataforma (maior contorno
    claro), as regiões escuras cuja área é compatível com o buraco físico
    informado. `expected_hole_area_fraction` — (diâmetro do buraco / diâmetro
    da arena)², já derivável dos dois `--*-diameter-cm` informados na criação
    da montagem — delimita essa área esperada; não é um valor arbitrário.

    Usada tanto por `_detect_holes_ring` (ajusta o círculo todo) quanto por
    `_snap_holes_to_detected_centers` (corrige buraco a buraco na
    confirmação) — a mesma varredura serve às duas correções.

    Returns:
        Lista de centros `(x_px, y_px)`, possivelmente vazia (sombra, reflexo
        ou o animal cobrindo buracos reduzem a contagem encontrada).
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    platform_contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not platform_contours:
        return []
    platform = max(platform_contours, key=cv2.contourArea)
    platform_area = cv2.contourArea(platform)
    if platform_area <= 0:
        return []

    mask = np.zeros(thresh.shape, dtype=np.uint8)
    cv2.drawContours(mask, [platform], -1, 255, -1)
    dark_inside = cv2.bitwise_and(cv2.bitwise_not(thresh), mask)

    # Abertura morfológica 3x3 — o menor kernel que ainda rompe uma ponte fina
    # de 1-2 px (sombra encostando no buraco, ou o buraco encostando na borda
    # da máscara da plataforma), sem erodir o próprio buraco. Testado contra
    # vídeo real: um kernel maior (5, 7) chega a apagar buracos pequenos por
    # completo em vez de só limpar a ponte — não é um ganho livre de subir o
    # tamanho.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    dark_inside = cv2.morphologyEx(dark_inside, cv2.MORPH_OPEN, kernel)

    # Margem generosa (0.2x a 6x da área esperada): o buraco no vídeo pode
    # parecer menor que o diâmetro físico (sombra parcial) ou maior
    # (penumbra ao redor), mas um ruído de poucos pixels ou o corpo do
    # animal ficam bem fora dessa faixa.
    min_area = 0.2 * expected_hole_area_fraction * platform_area
    max_area = 6.0 * expected_hole_area_fraction * platform_area

    centers: list[tuple[float, float]] = []
    hole_contours, _ = cv2.findContours(dark_inside, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in hole_contours:
        area = cv2.contourArea(contour)
        if not (min_area < area < max_area):
            continue
        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0 or 4 * math.pi * area / perimeter**2 < 0.5:
            continue  # descarta contornos alongados (sombra, pata, cauda)
        moments = cv2.moments(contour)
        if moments["m00"] == 0:
            continue
        centers.append((moments["m10"] / moments["m00"], moments["m01"] / moments["m00"]))
    return centers


def _detect_holes_ring(
    frame: np.ndarray, expected_hole_area_fraction: float
) -> tuple[float, float, float] | None:
    """Estima centro e raio da circunferência dos buracos a partir dos próprios buracos.

    `_detect_platform_circle` mede a borda física do disco; aqui o alvo é
    outro: `platform_radius_px` é o raio da circunferência *dos buracos*
    (é nela que `generate_holes` distribui os N buracos, RN06), e as duas
    circunferências só coincidem se a câmera for perfeitamente zenital e os
    buracos chegarem até a borda. Em geral não é o caso, e é por isso que o
    anel desenhado por `a` não cobre os buracos reais.

    Ajusta um círculo (mínimos quadrados) aos centros encontrados por
    `_detect_hole_candidates`. Precisa de ao menos 3 buracos detectados para
    isso (o mesmo mínimo geométrico de N em `generate_holes`). Serve só como
    ponto de partida: o operador ainda corrige arrastando o mouse, e
    `_snap_holes_to_detected_centers` refina buraco a buraco na confirmação.

    Returns:
        `(center_x_px, center_y_px, radius_px)`, ou `None` se menos de 3
        buracos plausíveis forem encontrados.
    """
    centers = _detect_hole_candidates(frame, expected_hole_area_fraction)
    if len(centers) < 3:
        return None
    return _fit_circle_to_points(centers)


def _snap_holes_to_detected_centers(
    geometry: MazeGeometry, centers: list[tuple[float, float]], max_offset_px: float
) -> tuple[MazeGeometry, int]:
    """Corrige cada buraco para o centro detectado mais próximo, dentro de uma tolerância.

    `_detect_holes_ring` só reposiciona o círculo todo (um centro, um raio);
    continua assumindo os N buracos igualmente espaçados nele. Esta função dá
    o passo que faltava: usa os mesmos candidatos (`_detect_hole_candidates`)
    para mover cada buraco, individualmente, para cima do buraco real mais
    próximo — o que corrige o desvio que sobra quando a câmera não é
    perfeitamente zenital e um lado da plataforma está mais comprimido que o
    outro. Buracos sem candidato próximo o bastante (sombra, animal, baixo
    contraste) ficam no círculo teórico, como antes.

    Pareamento é guloso e único (menor distância primeiro, cada buraco e cada
    candidato usados no máximo uma vez) para não haver dois buracos puxados
    para o mesmo ponto detectado. `angle_deg` é recalculado a partir da nova
    posição — nunca fica designado a um ponto diferente do que `x_px`/`y_px`
    informam, o que quebraria o referencial de sala (US-05).

    Chamada uma única vez, na confirmação (Enter/q/Esc) — nunca a cada quadro
    do ajuste ao vivo: um encaixe feito durante o arraste ficaria associado a
    um `hole_number` que deixa de fazer sentido se N ou o centro mudarem
    depois, e teria que ser invalidado a cada tecla.

    Args:
        geometry: Geometria confirmada pelo operador (círculo final).
        centers: Candidatos a buraco, de `_detect_hole_candidates` sobre o
            mesmo quadro.
        max_offset_px: Distância máxima para considerar um candidato o mesmo
            buraco — maior que isso, o candidato é de outro buraco ou ruído.

    Returns:
        Uma nova `MazeGeometry` com os buracos ajustados, e a contagem de
        buracos efetivamente corrigidos.
    """
    pairs = []
    for hole in geometry.holes:
        for center_index, (cx, cy) in enumerate(centers):
            distance = math.hypot(cx - hole.x_px, cy - hole.y_px)
            if distance <= max_offset_px:
                pairs.append((distance, hole.hole_number, center_index))
    pairs.sort()

    assigned_centers: dict[int, tuple[float, float]] = {}
    used_center_indices: set[int] = set()
    for _distance, hole_number, center_index in pairs:
        if hole_number in assigned_centers or center_index in used_center_indices:
            continue
        assigned_centers[hole_number] = centers[center_index]
        used_center_indices.add(center_index)

    if not assigned_centers:
        return geometry, 0

    snapped_holes = []
    for hole in geometry.holes:
        target = assigned_centers.get(hole.hole_number)
        if target is None:
            snapped_holes.append(hole)
            continue
        new_x, new_y = target
        angle_deg = math.degrees(
            math.atan2(new_y - geometry.center_y_px, new_x - geometry.center_x_px)
        )
        snapped_holes.append(
            Hole(
                hole_number=hole.hole_number,
                angle_deg=angle_deg % 360.0,
                x_px=new_x,
                y_px=new_y,
                radius_px=hole.radius_px,
                is_target=hole.is_target,
            )
        )
    return (
        MazeGeometry(
            center_x_px=geometry.center_x_px,
            center_y_px=geometry.center_y_px,
            platform_radius_px=geometry.platform_radius_px,
            holes=tuple(snapped_holes),
        ),
        len(assigned_centers),
    )


def _try_generate_geometry(state: dict) -> MazeGeometry | None:
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
            hole_radius_px=state["hole_radius"],
        )
    except GeometryValidationError:
        return None


def _apply_geometry_key(state: dict, key: int, frame: np.ndarray) -> bool:
    """Aplica uma tecla da janela de ajuste ao estado; True = confirmar e fechar.

    O raio do buraco ('['/']') é ajustável aqui porque não dá para derivá-lo
    de `--hole-diameter-cm` na criação da montagem: a escala px→cm (US-02) só
    é calibrada depois, sobre a montagem já criada. Ele precisa coincidir com
    o buraco real no quadro, pois as zonas de proximidade (Épico D) e a região
    "buraco" da anotação (US-06) são definidas em múltiplos dele (RN06).
    """
    if key in (ord("+"), ord("=")):
        state["hole_count"] = min(state["hole_count"] + 1, MAX_INTERACTIVE_HOLE_COUNT)
    elif key in (ord("-"), ord("_")):
        state["hole_count"] = max(state["hole_count"] - 1, 3)
    elif key == ord("]"):
        state["hole_radius"] += HOLE_RADIUS_STEP_PX
    elif key == ord("["):
        state["hole_radius"] = max(state["hole_radius"] - HOLE_RADIUS_STEP_PX, MIN_HOLE_RADIUS_PX)
    elif key == ord("a"):
        detected = _detect_platform_circle(frame)
        if detected is not None:
            center_x, center_y, radius = detected
            state["center"] = (center_x, center_y)
            state["radius"] = radius
    elif key == ord("h"):
        detected = _detect_holes_ring(frame, state["expected_hole_area_fraction"])
        if detected is not None:
            center_x, center_y, radius = detected
            state["center"] = (center_x, center_y)
            state["radius"] = radius
    elif key in (13, ord("q"), 27):  # 13 = Enter, 27 = Esc
        return True
    state["target"] = min(state["target"], state["hole_count"] - 1)
    return False


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
    arena_diameter_cm: float,
    hole_diameter_cm: float,
) -> tuple[MazeGeometry, int]:
    """Janela OpenCV para ajustar a geometria com o mouse (Cenário 1).

    Arrastar o botão esquerdo do centro real até o buraco físico de
    referência (US-05) define centro, raio e ângulo inicial de uma vez (o
    ângulo vem da direção do arraste) — esse buraco vira o buraco 0. Clicar com o botão direito perto de um buraco já desenhado
    marca aquele buraco como alvo. Teclas '+'/'-' mudam N e '['/']' mudam o
    raio do buraco ao vivo (ver `_apply_geometry_key`). Tecla
    'q'/Esc/Enter confirma e fecha a janela, retornando a última geometria
    válida exibida — combinações inválidas (ex.: N <= 2 durante o ajuste)
    simplesmente não substituem essa última geometria válida.

    Na confirmação, cada buraco é ainda corrigido para o candidato detectado
    mais próximo, dentro de `2 * hole_radius` (`_snap_holes_to_detected_centers`) —
    não a cada quadro do ajuste ao vivo, só uma vez, no fechamento da janela.

    Returns:
        A geometria final (já com o encaixe por buraco aplicado) e quantos
        buracos foram efetivamente corrigidos por ele.
    """
    window = "Ajuste da geometria - Barnes"
    cv2.namedWindow(window, cv2.WINDOW_AUTOSIZE)

    state = {
        "center": (center_x_px, center_y_px),
        "radius": platform_radius_px,
        "start_angle": start_angle_deg,
        "hole_count": hole_count,
        "target": target_hole_number,
        "hole_radius": max(hole_radius_px, MIN_HOLE_RADIUS_PX),
        "dragging": False,
        "expected_hole_area_fraction": (hole_diameter_cm / arena_diameter_cm) ** 2,
    }

    # No backend win32 do OpenCV, registrar o mouse callback antes do
    # primeiro imshow pode não vincular à superfície da janela (ela ainda
    # não existe de fato no SO) — o teclado funciona porque passa por
    # waitKey, não por esse hook. Por isso mostramos um primeiro quadro e
    # damos um waitKey(1) para "realizar" a janela antes de registrar.
    geometry = _try_generate_geometry(state)
    canvas = _draw_geometry_overlay(frame, geometry) if geometry is not None else frame.copy()
    cv2.imshow(window, canvas)
    cv2.waitKey(1)

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
            candidate = _try_generate_geometry(state)
            if candidate is not None:
                nearest = min(
                    candidate.holes, key=lambda h: math.hypot(h.x_px - x, h.y_px - y)
                )
                if math.hypot(nearest.x_px - x, nearest.y_px - y) <= nearest.radius_px * 2:
                    state["target"] = nearest.hole_number

    cv2.setMouseCallback(window, on_mouse)
    while True:
        key = cv2.waitKey(30) & 0xFF
        if _apply_geometry_key(state, key, frame):
            break

        candidate = _try_generate_geometry(state)
        if candidate is not None:
            geometry = candidate

        canvas = _draw_geometry_overlay(frame, geometry) if geometry is not None else frame.copy()
        for line_index, line in enumerate(reversed(_INSTRUCTIONS)):
            cv2.putText(
                canvas,
                line.format(n=state["hole_count"], r=state["hole_radius"]),
                (10, canvas.shape[0] - 10 - 18 * line_index),
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

    candidates = _detect_hole_candidates(frame, state["expected_hole_area_fraction"])
    return _snap_holes_to_detected_centers(
        geometry, candidates, max_offset_px=2 * state["hole_radius"]
    )


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
    start_angle_deg: float = typer.Option(
        0.0,
        help="Ângulo do buraco de índice 0, em graus. O buraco 0 deve ser o buraco físico de "
        "referência combinado com o laboratório (US-05) — ele ancora o referencial da sala.",
    ),
    target_hole_number: int = typer.Option(
        0, help="Índice do buraco-alvo, 0..N-1. Ajustável clicando com o botão direito."
    ),
    hole_radius_px: float = typer.Option(
        15.0,
        help="Raio de cada buraco, em pixels — base das zonas de proximidade (RN06). No modo "
        "interativo é só o valor inicial: ajuste com [ e ] até cobrir o buraco real; com "
        "--no-interactive, meça no quadro e informe.",
    ),
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
        with _command_errors():
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

    snapped_count = 0
    with _command_errors():
        if interactive:
            geometry, snapped_count = _adjust_geometry_interactively(
                frame,
                center_x_px=center_x,
                center_y_px=center_y,
                platform_radius_px=platform_radius_px,
                hole_count=hole_count,
                start_angle_deg=start_angle_deg,
                target_hole_number=target_hole_number,
                hole_radius_px=hole_radius_px,
                arena_diameter_cm=arena_diameter_cm,
                hole_diameter_cm=hole_diameter_cm,
            )

        try:
            with get_connection(dsn) as conn:
                maze_config_id = insert_maze_config(
                    conn,
                    experiment_id=experiment_id,
                    name=name,
                    arena_diameter_cm=arena_diameter_cm,
                    hole_diameter_cm=hole_diameter_cm,
                    geometry=geometry,
                )
        except psycopg.errors.ForeignKeyViolation as exc:
            raise ValueError(f"Experimento #{experiment_id} não existe.") from exc
    typer.echo(
        f"Montagem #{maze_config_id} salva no banco ({geometry.hole_count} buracos, "
        f"raio do buraco {geometry.holes[0].radius_px:.1f} px)."
    )
    if interactive:
        typer.echo(
            f"{snapped_count} de {geometry.hole_count} buracos ajustados automaticamente "
            "para o buraco real detectado; os demais ficaram na posição estimada pelo círculo."
        )


@maze_app.command("show")
def show_maze(
    maze_config_id: int = typer.Argument(..., help="Id da configuração de labirinto a carregar."),
    dsn: str = typer.Option(None, help="DSN do Postgres. Padrão: BARNES_DATABASE_URL."),
) -> None:
    """Carrega uma montagem do banco e imprime sua geometria, sem interação (RN05)."""
    with _command_errors(), get_connection(dsn) as conn:
        geometry = get_maze_config(conn, maze_config_id)

    typer.echo(f"Centro: ({geometry.center_x_px}, {geometry.center_y_px}) px")
    typer.echo(f"Raio da plataforma: {geometry.platform_radius_px} px")
    typer.echo(f"N buracos: {geometry.hole_count}")
    typer.echo(f"Raio do buraco: {geometry.holes[0].radius_px:.1f} px")
    typer.echo(f"Alvo: buraco #{geometry.target_hole.hole_number}")
    typer.echo("Buraco 0 = buraco físico de referência; ângulos de sala com rotação 0° (US-05).")
    for hole in geometry.holes:
        markers = (" (REF)" if hole.hole_number == 0 else "") + (" (ALVO)" if hole.is_target else "")
        room_angle = hole_to_room_angle(geometry, hole.hole_number, rotation_deg=0.0)
        typer.echo(
            f"  #{hole.hole_number}: angulo [imagem]={hole.angle_deg:.1f} "
            f"[sala]={room_angle:.1f} pos=({hole.x_px:.1f}, {hole.y_px:.1f}){markers}"
        )


# --- Calibração px→cm e métricas (US-02) --------------------------------------

Video = Annotated[Path, typer.Option("--video", help="Vídeo original do trial (.mp4).")]
Frame = Annotated[int, typer.Option("--frame", min=0, help="Índice do quadro, começando em zero.")]
MazeConfigId = Annotated[
    int, typer.Option("--maze-config-id", help="Id da montagem (maze_configs) a calibrar/usar.")
]


@contextmanager
def _command_errors():
    """Traduz os erros esperados de um comando em mensagem + código de saída, sem traceback.

    Usado por todos os comandos: um erro de operação (vídeo ilegível, trial
    inexistente, banco fora do ar) nunca deve aparecer como traceback do Python.
    """
    try:
        yield
    except typer.Exit:
        raise
    except DatabaseConfigError as exc:
        # A mensagem só explica como configurar; não contém a string de conexão.
        typer.echo(f"Erro: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except GeometryValidationError as exc:
        typer.echo(f"Erro no parâmetro '{exc.field}': {exc}", err=True)
        raise typer.Exit(code=1) from exc
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
        first, second = collect_segments(reference)
        length_a = _length(length_1_cm, "Comprimento real do segmento 1 (cm)")
        length_b = _length(length_2_cm, "Comprimento real do segmento 2 (cm)")
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
    trajectory: Annotated[
        Path,
        typer.Option(
            "--trajectory", help="CSV com x_px,y_px,time_s (time_s desde o início do vídeo)."
        ),
    ],
    trial: Annotated[int, typer.Option("--trial", help="Id do trial (trials.id).")],
    maze_config_id: Annotated[
        int | None,
        typer.Option(
            "--maze-config-id",
            help="Opcional: a montagem vem do próprio trial; se informada, precisa ser a dele.",
        ),
    ] = None,
    frame: Frame = 0,
    ideal_distance_px: Annotated[
        float | None,
        typer.Option(
            "--ideal-distance-px", help="Distância ideal em pixels para eficiência de rota."
        ),
    ] = None,
    dsn: str = typer.Option(None, help="DSN do Postgres. Padrão: BARNES_DATABASE_URL."),
) -> None:
    """Calcular métricas de uma trajetória já extraída e registrar a execução (US-02, US-27).

    Usa a montagem do próprio trial e só as amostras dentro do intervalo útil
    gravado nele (US-03 RN02). O vídeo informado precisa ter o hash do trial
    catalogado (US-27 RN04); a execução — limiares, parâmetros, commit e
    estado sujo — e as métricas são gravadas juntas (US-27 RN01/RN02).
    """
    started_at = datetime.now(UTC)
    with _command_errors():
        # Sem trial válido, intervalo ou escala, nem o vídeo é decodificado nem o CSV é lido.
        with get_connection(dsn) as conn:
            stored = get_trial(conn, trial)
            if maze_config_id is not None and maze_config_id != stored.maze_config_id:
                raise ValueError(
                    f"O trial #{trial} é da montagem #{stored.maze_config_id}, não da "
                    f"#{maze_config_id}: a escala de outra montagem não vale para ele. "
                    "Omita --maze-config-id."
                )
            if stored.interval is None:
                raise ValueError(
                    f"O trial #{trial} não tem intervalo útil registrado (US-03), então não dá "
                    "para garantir que nada fora dele entre nas métricas. Recarregue o vídeo "
                    "com `barnes video load`."
                )
            calibration = require_calibration(conn, stored.maze_config_id)
        check = verify_video_file(video, stored.content_hash)
        if check.status is not FileStatus.OK:
            raise ValueError(
                f"O vídeo informado não é o catalogado no trial #{trial}: o conteúdo "
                "difere do registrado (hash). Confira --video; reprocessar com outro "
                "arquivo produziria métricas atribuídas ao trial errado."
            )
        moved = video.resolve() != Path(stored.filepath).resolve()
        if moved:
            typer.echo(
                f"Aviso: trial #{trial} catalogado em {stored.filepath}, mas o mesmo vídeo "
                f"(hash idêntico) foi informado em {video}. O caminho novo fica registrado "
                "na execução.",
                err=True,
            )
        reference = read_frame(video, frame)
        frame_size = (reference.shape[1], reference.shape[0])
        if frame_size != (stored.width_px, stored.height_px):
            raise ValueError(
                f"O vídeo informado tem resolução {frame_size}, mas o trial #{trial} foi "
                f"gravado em {(stored.width_px, stored.height_px)}: confira --video."
            )
        # Resolução incompatível também falha antes de ler o CSV da trajetória inteiro.
        validate_frame_size(calibration, frame_size)
        points, times = _read_trajectory(trajectory)
        metrics = process_trial(
            calibration.cm_per_px,
            points,
            times,
            frame_size=frame_size,
            interval=stored.interval,
            ideal_distance_px=ideal_distance_px,
        )
        thresholds = thresholds_snapshot()
        source = git_revision_record(PACKAGE_DIR)
        git = GitState.from_record(source)
        px_per_10cm = 10 / calibration.cm_per_px
        parameters = {
            "comando": "metrics process",
            "video": str(video),
            "video_catalogado": str(stored.filepath),
            "video_movido": moved,
            "trajectory": str(trajectory),
            "trajectory_sha256": file_sha256(trajectory),
            "frame": frame,
            "ideal_distance_px": ideal_distance_px,
            "px_per_10cm": px_per_10cm,
            "interval": asdict(stored.interval),
        }
        with get_connection(dsn) as conn:
            # Execução e métricas na mesma transação: nunca uma sem a outra.
            execucao_id = record_processing_execution(
                conn,
                trial_id=trial,
                maze_config_id=stored.maze_config_id,
                parameters=parameters,
                thresholds=thresholds,
                git=git,
                video_hash=check.actual_hash,
                started_at=started_at,
                duration_seconds=(datetime.now(UTC) - started_at).total_seconds(),
                metadata={"source": source},
            )
            insert_trial_result(
                conn,
                trial,
                execucao_id=execucao_id,
                distance_cm=metrics["distance_cm"],
                speed_mean_cm=metrics["mean_speed_cm_s"],
                route_efficiency=metrics.get("route_efficiency"),
                px_per_10cm_used=px_per_10cm,
                calculated_at=datetime.now(UTC),
            )
        if not git.reproducible:
            typer.echo(
                f"Aviso: execução #{execucao_id} registrada com repositório "
                f"{'sujo (alterações não commitadas)' if git.dirty else 'em estado desconhecido'}"
                " — o resultado não é reproduzível pelo commit.",
                err=True,
            )
        typer.echo(json.dumps(metrics | {"execucao_id": execucao_id}, ensure_ascii=False, indent=2))


@metrics_app.command("executions")
def executions(
    trial: Annotated[int | None, typer.Option("--trial", help="Filtrar por id do trial.")] = None,
    history: Annotated[
        bool,
        typer.Option("--history", help="Com --trial: todos os cálculos, não só o atual (US-27)."),
    ] = False,
    dsn: str = typer.Option(None, help="DSN do Postgres. Padrão: BARNES_DATABASE_URL."),
) -> None:
    """Consultar resultados calculados e se ficaram obsoletos após recalibração (RN05).

    Cada resultado traz `execucao_id`; `barnes execution show ID` mostra modelo,
    limiares, parâmetros e commit daquela execução (US-27).
    """
    with _command_errors():
        if history and trial is None:
            raise ValueError("--history exige --trial.")
        with get_connection(dsn) as conn:
            if history:
                rows = list_trial_result_history(conn, trial)
            elif trial is not None:
                result = get_trial_result(conn, trial)
                rows = [] if result is None else [result]
            else:
                rows = list_trial_results(conn)
        typer.echo(json.dumps([asdict(row) for row in rows], ensure_ascii=False, indent=2, default=str))


@execution_app.command("show")
def execution_show(
    execution_id: Annotated[int, typer.Argument(help="Id da execução (execucao.id).")],
    dsn: str = typer.Option(None, help="DSN do Postgres. Padrão: BARNES_DATABASE_URL."),
) -> None:
    """Mostrar tudo o que uma execução registrou: modelo, limiares, parâmetros e commit (US-27).

    É o que basta para reprocessar um resultado antigo (Cenário 2): fazer
    checkout de `git_commit`, restaurar `limiares` em `configs/default.yaml` e
    repetir o comando com `parametros`. `reproduzivel` é falso se o
    repositório estava sujo ou sem git na hora da execução (RN05).
    """
    with _command_errors():
        with get_connection(dsn) as conn:
            stored = get_execution(conn, execution_id)
        if not stored.reproducible:
            typer.echo(
                f"Aviso: execução #{execution_id} não é reproduzível pelo commit "
                "(repositório sujo, sem git ou anterior à US-27).",
                err=True,
            )
        typer.echo(
            json.dumps(
                asdict(stored) | {"reproduzivel": stored.reproducible},
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )


@catalog_app.command("list")
def catalog_list(
    experiment_id: Annotated[
        int | None, typer.Option("--experiment-id", help="Só os trials deste experimento.")
    ] = None,
    verify_hash: Annotated[
        bool,
        typer.Option(
            "--verificar-hash",
            help="Reler cada vídeo e comparar o conteúdo (lento). Padrão: só existência e tamanho.",
        ),
    ] = False,
    no_file_check: Annotated[
        bool, typer.Option("--sem-arquivo", help="Não conferir os vídeos no disco.")
    ] = False,
    search_dirs: Annotated[
        list[Path] | None,
        typer.Option("--procurar-em", help="Pasta extra onde procurar vídeos movidos (repetível)."),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Saída em JSON.")] = False,
    dsn: str = typer.Option(None, help="DSN do Postgres. Padrão: BARNES_DATABASE_URL."),
) -> None:
    """Listar trials com animal, sessão, situação, cobertura de pose e conferência do vídeo.

    Um vídeo movido, renomeado, substituído ou ausente é sinalizado com o id
    do trial (US-27 RN04); a listagem não altera nada no banco.
    """
    if verify_hash and no_file_check:
        raise typer.BadParameter("--verificar-hash e --sem-arquivo são exclusivos.")
    verify = None if no_file_check else ("hash" if verify_hash else "size")
    with _command_errors():
        with get_connection(dsn) as conn:
            entries = list_catalog(
                conn, experiment_id=experiment_id, verify=verify, search_dirs=search_dirs or ()
            )
        if as_json:
            typer.echo(json.dumps([_catalog_json(e) for e in entries], ensure_ascii=False,
                                  indent=2, default=str))
        else:
            _print_catalog(entries)
        divergent = [e for e in entries if e.diverges]
        for entry in divergent:
            typer.echo(f"Divergência no trial #{entry.trial_id}: {entry.arquivo.describe()}.",
                       err=True)
        if divergent:
            typer.echo(
                f"{len(divergent)} trial(s) com vídeo divergente do catalogado. Não reprocesse "
                "antes de conferir o arquivo.",
                err=True,
            )


def _catalog_json(entry) -> dict:
    data = asdict(entry)
    data["arquivo"] = None if entry.arquivo is None else entry.arquivo.status.value
    data["arquivo_detalhe"] = None if entry.arquivo is None else entry.arquivo.describe()
    data["arquivo_divergente"] = entry.diverges
    return data


def _print_catalog(entries) -> None:
    if not entries:
        typer.echo("Nenhum trial catalogado.")
        return
    header = ("trial", "animal", "sessão", "fase", "nº", "situação", "cobertura", "fps",
              "execução", "arquivo")
    rows = [
        (
            f"#{e.trial_id}",
            e.animal or "—",
            str(e.sessao),
            e.fase,
            str(e.trial_no_dia),
            e.situacao.value,
            "—" if e.cobertura_pose is None else f"{e.cobertura_pose:.1%}",
            "variável" if e.fps_variavel else "ok",
            "—" if e.execucao_id is None else f"#{e.execucao_id}",
            "—" if e.arquivo is None else e.arquivo.status.value,
        )
        for e in entries
    ]
    widths = [max(len(r[i]) for r in (header, *rows)) for i in range(len(header))]
    for row in (header, *rows):
        typer.echo("  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)))


ANNOTATIONS_DIR = Path("data/annotations")
ConfigPath = Annotated[
    Path, typer.Option("--config", help="YAML com a seção 'anotacao' do protocolo.")
]
AnnotationsPath = Annotated[
    Path, typer.Option("--annotations", help="Conjunto anotado no formato interno.")
]
ManifestPath = Annotated[Path, typer.Option("--manifest", help="Manifesto da divisão.")]


@pose_app.command("series")
def pose_series(
    trial: Annotated[int, typer.Option("--trial", help="Id do trial (trials.id).")],
    inference: Annotated[
        Path,
        typer.Option(
            "--inference",
            help="Diretório da execução de `barnes pose infer` (com execucao.json e pose.csv).",
        ),
    ],
    out: Annotated[
        Path, typer.Option("--out", help="Pasta das trajetórias (um .parquet por trial).")
    ] = Path("data/interim"),
    dsn: str = typer.Option(None, help="DSN do Postgres. Padrão: BARNES_DATABASE_URL."),
) -> None:
    """Gerar a série (x, y, theta, t) do trial a partir da pose inferida (US-09).

    Lê o `pose.csv` de uma inferência concluída do próprio trial (hash e montagem
    conferidos), converte para cm com a escala da montagem (US-02), calcula theta pelo
    eixo centro do corpo -> focinho e grava `<out>/trial_<id>.parquet` no contrato
    de `docs/contrato-trajetoria.md`. Quadro sem pose fica marcado como ausente. A
    execução (US-27) e o caminho do arquivo são gravados na mesma transação.
    """
    started_at = datetime.now(UTC)
    with _command_errors():
        record = load_inference_record(inference)  # confere os hashes dos artefatos
        if record["kind"] != INFERENCE_RECORD_KIND or record["status"] != "completed":
            raise ValueError(
                f"{inference} não é uma inferência de trial concluída (status: "
                f"{record['status']}). Rode `barnes pose infer` de novo."
            )
        if record.get("trial_id") != trial:
            raise ValueError(
                f"A inferência em {inference} é do trial #{record.get('trial_id')}, não do #{trial}."
            )
        with get_connection(dsn) as conn:
            stored = get_trial(conn, trial)
            calibration = require_calibration(conn, stored.maze_config_id)
        if stored.interval is None:
            raise ValueError(f"O trial #{trial} não tem intervalo útil registrado (US-03).")
        if record.get("content_hash") != stored.content_hash:
            raise ValueError(
                f"A inferência foi feita sobre um vídeo com outro conteúdo que o do trial "
                f"#{trial} (hash diverge): a pose não é deste trial."
            )
        if record.get("maze_config_id") != stored.maze_config_id:
            raise ValueError(
                f"A inferência usou um modelo da montagem #{record.get('maze_config_id')}, "
                f"mas o trial #{trial} é da montagem #{stored.maze_config_id}."
            )
        if not math.isclose(record["fps"], stored.fps_real, rel_tol=1e-9):
            raise ValueError(
                f"A inferência usou fps {record['fps']}, mas o trial #{trial} registra "
                f"{stored.fps_real}: refaça a inferência."
            )
        # A pose está em pixels do vídeo original; a escala só vale nessa resolução.
        validate_frame_size(calibration, (stored.width_px, stored.height_px))
        frames = record["processed_interval_frames"]
        pose_csv = Path(inference) / "pose.csv"
        pose = read_pose_csv(pose_csv)
        if stored.fps_is_variable:
            typer.echo(
                f"Aviso: o vídeo do trial #{trial} tem fps variável (US-01) — os tempos t_s "
                "da série são aproximados. O aviso vai junto no arquivo (fps_variavel).",
                err=True,
            )

        destination = trajectory_path(out, trial)
        source = git_revision_record(PACKAGE_DIR)
        git = GitState.from_record(source)
        parameters = {
            "comando": "pose series",
            "inference_run": str(Path(inference).resolve()),
            "inference_run_id": Path(inference).resolve().name,
            "pose_csv_sha256": file_sha256(pose_csv),
            "processed_interval_frames": frames,
            "cm_per_px": calibration.cm_per_px,
            "px_per_10cm": 10 / calibration.cm_per_px,
            "fps_real": stored.fps_real,
            "fps_variavel": bool(stored.fps_is_variable),
            "interval": asdict(stored.interval),
            "saida": str(destination),
        }
        with get_connection(dsn) as conn:
            # Execução, arquivo e trials.trajectory_path juntos: uma falha ao gravar
            # o Parquet desfaz a execução.
            execucao_id = record_processing_execution(
                conn,
                trial_id=trial,
                maze_config_id=stored.maze_config_id,
                parameters=parameters,
                thresholds=thresholds_snapshot(),
                git=git,
                video_hash=stored.content_hash,
                started_at=started_at,
                model_id=record["model_id"],
                artifact_path=str(destination),
                metadata={"source": source},
            )
            table = build_series(
                pose,
                trial_id=trial,
                execucao_id=execucao_id,
                expected_frames=(frames["start"], frames["end"]),
                fps=stored.fps_real,
                interval=stored.interval,
                fps_variable=bool(stored.fps_is_variable),
                cm_per_px=calibration.cm_per_px,
                content_hash=stored.content_hash,
                model_id=record["model_id"],
                generated_at=started_at,
            )
            write_trajectory(table, destination)
            set_trajectory_path(conn, trial, str(destination))
        without_pose = table.num_rows - sum(table.column("pose_valida").to_pylist())
        if not git.reproducible:
            typer.echo(
                f"Aviso: execução #{execucao_id} registrada com repositório "
                f"{'sujo (alterações não commitadas)' if git.dirty else 'em estado desconhecido'}"
                " — o resultado não é reproduzível pelo commit.",
                err=True,
            )
        typer.echo(
            f"Trajetória: {destination} | {table.num_rows} quadros, {without_pose} sem pose "
            f"válida | execução #{execucao_id}"
        )


@pose_app.command("sample")
def pose_sample(
    video: Video,
    maze_config_id: MazeConfigId,
    start_frame: Annotated[
        int | None,
        typer.Option(
            "--start-frame",
            min=0,
            help="Início do intervalo útil (US-03). Omitido: detecção automática da soltura.",
        ),
    ] = None,
    end_frame: Annotated[
        int | None,
        typer.Option("--end-frame", min=0, help="Fim do intervalo útil. Omitido: fim do vídeo."),
    ] = None,
    scan_step: Annotated[
        int, typer.Option("--scan-step", min=1, help="Varre um a cada N quadros.")
    ] = 5,
    out_dir: Annotated[
        Path, typer.Option("--out", help="Diretório base dos quadros exportados.")
    ] = ANNOTATIONS_DIR,
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite",
            help="Apaga os PNGs de uma amostragem anterior deste trial (podem estar anotados).",
        ),
    ] = False,
    config: ConfigPath = DEFAULT_CONFIG_PATH,
    dsn: str = typer.Option(None, help="DSN do Postgres. Padrão: BARNES_DATABASE_URL."),
) -> None:
    """Escolher e exportar quadros de um trial para anotar, cobrindo as 3 regiões (RN02)."""
    with _command_errors():
        protocol = load_annotation_protocol(config)
        metadata = load_trial_video(video)
        # Recusa antes da varredura, que num vídeo real leva minutos.
        check_previous_export(metadata.content_hash, out_dir, overwrite=overwrite)
        try:
            interval = build_trial_interval(metadata, start_frame=start_frame, end_frame=end_frame)
        except TrialIntervalError as exc:
            raise ValueError(f"Intervalo útil: {exc}") from exc
        _print_interval(interval)
        with get_connection(dsn) as conn:
            geometry = get_maze_config(conn, maze_config_id)

        result = sample_frames(
            video,
            geometry,
            protocol,
            frame_count=metadata.frame_count,
            start_frame=interval.start_frame,
            end_frame=min(interval.end_frame, metadata.frame_count - 1),
            scan_step=scan_step,
        )
        trial_dir = export_frames(
            video,
            metadata.content_hash,
            result.frames,
            out_dir,
            maze_config_id=maze_config_id,
            overwrite=overwrite,
        )

        rate = result.detected / result.scanned if result.scanned else 0.0
        typer.echo(
            f"Quadros varridos: {result.scanned} | animal encontrado por contraste em "
            f"{result.detected} ({rate:.1%})"
        )
        for region, wanted in protocol.frames_per_region.items():
            line = (
                f"  {region.value:<7} escolhidos {wanted - result.shortfall[region]}/{wanted} "
                f"(candidatos: {result.candidates[region]})"
            )
            if result.shortfall[region]:
                line += " — FALTARAM quadros nesta região"
            typer.echo(line)
        typer.echo(f"{len(result.frames)} quadros exportados em {trial_dir}")


@pose_app.command("import-slp")
def pose_import_slp(
    slp: Annotated[
        list[Path],
        typer.Argument(help="Um ou mais projetos do SLEAP (.slp) — ex.: um por anotador."),
    ],
    out: Annotated[
        Path, typer.Option("--out", help="CSV de saída no formato interno.")
    ] = ANNOTATIONS_DIR / ANNOTATIONS_CSV,
) -> None:
    """Converter as anotações do SLEAP para o formato interno, exigindo os 3 pontos (Cenário 1)."""
    with _command_errors():
        try:
            frames = [frame for path in slp for frame in from_slp(path)]
        except ImportError as exc:
            raise RuntimeError(str(exc)) from exc
        validate_complete(frames)
        write_annotations_csv(frames, out)
        trials = len({frame.trial for frame in frames})
        typer.echo(f"{len(frames)} quadros anotados de {trials} trial(s) gravados em {out}")


@pose_app.command("split")
def pose_split(
    annotations: AnnotationsPath = ANNOTATIONS_DIR / ANNOTATIONS_CSV,
    out: Annotated[
        Path, typer.Option("--out", help="Manifesto de saída.")
    ] = ANNOTATIONS_DIR / SPLIT_CSV,
    config: ConfigPath = DEFAULT_CONFIG_PATH,
) -> None:
    """Dividir o conjunto anotado em treino/validação/teste por trial (RN03)."""
    with _command_errors():
        protocol = load_annotation_protocol(config)
        frames = read_annotations_csv(annotations)
        validate_complete(frames)
        assignment = split_by_trial((f.trial for f in frames), protocol.split, protocol.seed)
        rows = build_manifest(frames, assignment)
        check_no_leakage(rows)
        write_manifest(rows, out)
        typer.echo(f"Divisão gravada em {out} (semente {protocol.seed}):")
        for subset, (trials, count) in summarize(rows).items():
            typer.echo(f"  {subset:<9} {trials} trial(s), {count} quadros")
        typer.echo("Verificação de vazamento: OK — nenhum trial em mais de um conjunto.")


@pose_app.command("check-split")
def pose_check_split(manifest: ManifestPath = ANNOTATIONS_DIR / SPLIT_CSV) -> None:
    """Verificar que nenhum trial tem quadros em mais de um conjunto (Cenário 3)."""
    with _command_errors():
        check_no_leakage(read_manifest(manifest))
        typer.echo("Verificação de vazamento: OK — nenhum trial em mais de um conjunto.")


@pose_app.command("report")
def pose_report(
    maze_config_id: Annotated[
        int | None,
        typer.Option(
            "--maze-config-id",
            help="Montagem para trials sem registro em amostragem.csv. Omitido: a de cada trial.",
        ),
    ] = None,
    annotations: AnnotationsPath = ANNOTATIONS_DIR / ANNOTATIONS_CSV,
    samples_dir: Annotated[
        Path,
        typer.Option("--samples", help="Diretório com <trial>/amostragem.csv de `pose sample`."),
    ] = ANNOTATIONS_DIR,
    config: ConfigPath = DEFAULT_CONFIG_PATH,
    dsn: str = typer.Option(None, help="DSN do Postgres. Padrão: BARNES_DATABASE_URL."),
) -> None:
    """Contar os quadros anotados por região, pelo centro do corpo anotado (Cenário 2)."""
    with _command_errors():
        protocol = load_annotation_protocol(config)
        frames = read_annotations_csv(annotations)
        validate_complete(frames)
        trials = {frame.trial for frame in frames}
        recorded = {trial: read_sampled_maze_config(samples_dir / trial) for trial in trials}
        montagens = resolve_maze_configs(trials, recorded, maze_config_id)
        with get_connection(dsn) as conn:
            by_id = {i: get_maze_config(conn, i) for i in sorted(set(montagens.values()))}
        geometries = {trial: by_id[montagens[trial]] for trial in trials}
        counts = count_by_region(frames, geometries, protocol.regions)
        typer.echo(f"Montagem(ns) usada(s): {', '.join(str(i) for i in by_id)}")
        typer.echo(f"Quadros anotados: {len(frames)}")
        for count in counts:
            typer.echo(f"  {count.region.value:<7} {count.frames:>5}  ({count.proportion:.1%})")
        missing = empty_regions(counts)
        if missing:
            names = ", ".join(region.value for region in missing)
            typer.echo(f"Reprovado: nenhuma anotação na(s) região(ões) {names}.", err=True)
            raise typer.Exit(code=1)
        typer.echo("Cobertura OK: as três regiões têm quadros anotados.")


register_pose_commands(pose_app, _command_errors)

if __name__ == "__main__":
    app()
