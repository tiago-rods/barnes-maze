"""Amostragem de quadros para anotação, estratificada por região (US-06 RN02).

Ainda não existe modelo de pose quando a anotação acontece — é ela que vai
treiná-lo. Para saber em que região o animal está em cada quadro, a posição
é estimada por **segmentação por contraste**: o fundo é a mediana de quadros
espalhados pelo trial (o animal, que se move, some da mediana), e o animal é
a maior região que difere desse fundo dentro da plataforma.

A estimativa serve só para *escolher* quadros. A contagem final por região
(Cenário 2) usa o ponto "centro do corpo" anotado — ver `barnes.pose.report`.
De quebra, a taxa de quadros em que a estimativa funciona é um primeiro dado
para a hipótese (a) da RN07: se a segmentação por contraste bastar, talvez
não seja preciso treinar modelo.
"""

from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from barnes.geometry.holes import MazeGeometry
from barnes.io.video import VideoLoadError, read_frame
from barnes.pose.annotations import FRAMES_DIR, frame_filename, trial_key
from barnes.pose.protocol import AnnotationProtocol
from barnes.pose.regions import Region, classify_region

# Quantos quadros espalhados pelo trial formam a mediana do fundo. Precisa ser
# grande o bastante para o animal não aparecer na mesma posição na maioria
# deles; poucas dezenas bastam e mantêm o custo de leitura baixo.
_BACKGROUND_FRAMES = 25

# A busca pelo animal fica restrita a um disco um pouco maior que a
# circunferência dos buracos: os buracos ficam perto da borda e o animal pode
# passar além deles, mas mãos e objetos fora da plataforma não contam.
_SEARCH_RADIUS_FRAC = 1.2

# Desvios-padrão acima da diferença média para um pixel contar como "animal".
# Mesmo critério relativo de `barnes.io.trim`: não depende da exposição de
# cada gravação, que varia entre sessões.
_DIFF_THRESHOLD_STD = 4.0

# Piso absoluto para o limiar acima (níveis de cinza, 0-255): num quadro sem
# animal a diferença é só ruído de compressão, com desvio quase nulo, e o
# limiar relativo sozinho marcaria esse ruído como animal.
_MIN_DIFF_LEVEL = 15.0

# Área mínima do blob, como fração da área do disco de busca. Descarta
# reflexos e ruído isolado; um camundongo ocupa bem mais que isso.
_MIN_BLOB_AREA_FRAC = 0.0005

SAMPLING_CSV = "amostragem.csv"


@dataclass(frozen=True)
class SampledFrame:
    """Um quadro escolhido para anotação.

    Attributes:
        frame_index: Índice do quadro no vídeo original.
        region: Região estimada pela segmentação por contraste.
        x_px: Coordenada x estimada do animal, em pixels.
        y_px: Coordenada y estimada do animal, em pixels.
    """

    frame_index: int
    region: Region
    x_px: float
    y_px: float


@dataclass(frozen=True)
class SamplingResult:
    """Resultado da amostragem de um trial.

    Attributes:
        frames: Quadros escolhidos, ordenados por índice.
        candidates: Quantos quadros varridos caíram em cada região.
        shortfall: Quantos quadros faltaram para atingir a meta de cada
            região (0 = meta atingida). Região com falta precisa de outro
            trial ou de outra rodada de amostragem.
        scanned: Quantos quadros foram varridos.
        detected: Em quantos deles o animal foi encontrado.
    """

    frames: tuple[SampledFrame, ...]
    candidates: dict[Region, int]
    shortfall: dict[Region, int]
    scanned: int
    detected: int


def _gray(frame: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    return cv2.GaussianBlur(gray, (5, 5), 0)


def _search_mask(shape: tuple[int, int], geometry: MazeGeometry) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    center = (round(geometry.center_x_px), round(geometry.center_y_px))
    radius = max(round(geometry.platform_radius_px * _SEARCH_RADIUS_FRAC), 1)
    cv2.circle(mask, center, radius, 255, -1)
    return mask


def build_background(video_path: str | Path, start_frame: int, end_frame: int) -> np.ndarray:
    """Estima o fundo (plataforma sem o animal) pela mediana de quadros espalhados.

    Args:
        video_path: Caminho do vídeo do trial.
        start_frame: Primeiro quadro considerado.
        end_frame: Último quadro considerado (inclusivo).

    Returns:
        O fundo em tons de cinza, já suavizado.

    Raises:
        VideoLoadError: Se nenhum quadro do intervalo puder ser lido.
    """
    count = min(_BACKGROUND_FRAMES, end_frame - start_frame + 1)
    indices = np.linspace(start_frame, end_frame, num=max(count, 1)).round().astype(int)
    frames = []
    for index in sorted(set(indices.tolist())):
        try:
            frames.append(_gray(read_frame(video_path, index)))
        except VideoLoadError:
            continue
    if not frames:
        raise VideoLoadError(f"Nenhum quadro legível entre {start_frame} e {end_frame}.")
    return np.median(np.stack(frames), axis=0).astype(np.uint8)


def estimate_animal_position(
    frame: np.ndarray, background: np.ndarray, geometry: MazeGeometry
) -> tuple[float, float] | None:
    """Estima a posição do animal num quadro por diferença em relação ao fundo.

    Args:
        frame: Quadro BGR (ou cinza) do vídeo.
        background: Fundo de `build_background`.
        geometry: Geometria da montagem, que limita a busca à plataforma.

    Returns:
        `(x_px, y_px)` do centróide do animal, ou `None` se nenhum blob
        grande o bastante for encontrado.
    """
    gray = _gray(frame)
    mask = _search_mask(gray.shape, geometry)
    diff = cv2.absdiff(gray, background)
    inside = diff[mask > 0]
    if inside.size == 0:
        return None
    threshold = max(float(inside.mean() + _DIFF_THRESHOLD_STD * inside.std()), _MIN_DIFF_LEVEL)
    binary = np.where((diff > threshold) & (mask > 0), 255, 0).astype(np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    search_area = math.pi * (geometry.platform_radius_px * _SEARCH_RADIUS_FRAC) ** 2
    if cv2.contourArea(largest) < search_area * _MIN_BLOB_AREA_FRAC:
        return None
    moments = cv2.moments(largest)
    if moments["m00"] == 0:
        return None
    return moments["m10"] / moments["m00"], moments["m01"] / moments["m00"]


def _scan(
    video_path: Path,
    geometry: MazeGeometry,
    protocol: AnnotationProtocol,
    background: np.ndarray,
    start_frame: int,
    end_frame: int,
    scan_step: int,
) -> tuple[list[SampledFrame], int]:
    capture = cv2.VideoCapture(str(video_path))
    candidates: list[SampledFrame] = []
    scanned = 0
    try:
        if not capture.isOpened():
            raise VideoLoadError(f"Não foi possível abrir o vídeo: {video_path}")
        if start_frame:
            capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        index = start_frame
        while index <= end_frame:
            if (index - start_frame) % scan_step == 0:
                ok, frame = capture.read()
                if not ok:
                    break
                scanned += 1
                position = estimate_animal_position(frame, background, geometry)
                if position is not None:
                    region = classify_region(*position, geometry, protocol.regions)
                    candidates.append(SampledFrame(index, region, *position))
            elif not capture.grab():
                break
            index += 1
    finally:
        capture.release()
    return candidates, scanned


def _select(
    candidates: list[SampledFrame], protocol: AnnotationProtocol
) -> tuple[list[SampledFrame], dict[Region, int]]:
    """Sorteia quadros por região respeitando o espaçamento mínimo entre eles.

    As regiões são preenchidas da mais rara para a mais comum, para que um
    quadro raro (perto de buraco) não seja bloqueado pelo espaçamento de um
    quadro comum (centro) escolhido antes.
    """
    rng = random.Random(protocol.seed)
    by_region = {region: [c for c in candidates if c.region is region] for region in Region}
    chosen: list[SampledFrame] = []
    shortfall: dict[Region, int] = {}
    for region in sorted(Region, key=lambda r: len(by_region[r])):
        pool = by_region[region][:]
        rng.shuffle(pool)
        wanted = protocol.frames_per_region[region]
        taken = 0
        for candidate in pool:
            if taken >= wanted:
                break
            if all(
                abs(candidate.frame_index - other.frame_index) >= protocol.min_gap_frames
                for other in chosen
            ):
                chosen.append(candidate)
                taken += 1
        shortfall[region] = wanted - taken
    return sorted(chosen, key=lambda f: f.frame_index), shortfall


def sample_frames(
    video_path: str | Path,
    geometry: MazeGeometry,
    protocol: AnnotationProtocol,
    *,
    frame_count: int,
    start_frame: int = 0,
    end_frame: int | None = None,
    scan_step: int = 5,
) -> SamplingResult:
    """Escolhe os quadros de um trial a anotar, cobrindo as três regiões (RN02).

    Args:
        video_path: Caminho do vídeo do trial.
        geometry: Geometria da montagem do trial (US-04).
        protocol: Protocolo de anotação (quantidades, espaçamento, semente).
        frame_count: Número de quadros do vídeo (`VideoMetadata.frame_count`).
        start_frame: Primeiro quadro considerado — use o início do intervalo
            útil (US-03) para não anotar a mão soltando o animal.
        end_frame: Último quadro considerado (inclusivo); padrão é o último
            quadro do vídeo.
        scan_step: Varre um a cada `scan_step` quadros. Só afeta o custo da
            varredura; o espaçamento entre quadros escolhidos é o do protocolo.

    Returns:
        Os quadros escolhidos e o diagnóstico da varredura.

    Raises:
        ValueError: Se o intervalo ou o passo forem inválidos.
        VideoLoadError: Se o vídeo não puder ser lido.
    """
    video_path = Path(video_path)
    end_frame = frame_count - 1 if end_frame is None else end_frame
    if scan_step < 1:
        raise ValueError("O passo de varredura deve ser >= 1.")
    if not 0 <= start_frame <= end_frame < frame_count:
        raise ValueError(
            f"Intervalo de quadros inválido: {start_frame}..{end_frame} "
            f"(o vídeo tem {frame_count} quadros)."
        )

    background = build_background(video_path, start_frame, end_frame)
    candidates, scanned = _scan(
        video_path, geometry, protocol, background, start_frame, end_frame, scan_step
    )
    chosen, shortfall = _select(candidates, protocol)
    return SamplingResult(
        frames=tuple(chosen),
        candidates={r: sum(c.region is r for c in candidates) for r in Region},
        shortfall=shortfall,
        scanned=scanned,
        detected=len(candidates),
    )


def export_frames(
    video_path: str | Path,
    content_hash: str,
    frames: tuple[SampledFrame, ...] | list[SampledFrame],
    out_dir: str | Path,
) -> Path:
    """Grava os quadros escolhidos como PNG, prontos para importar no SLEAP.

    Estrutura: `<out_dir>/<trial>/quadros/quadro_NNNNNN.png` mais
    `<out_dir>/<trial>/amostragem.csv`, em que `<trial>` é a chave curta do
    hash de conteúdo do vídeo (`trial_key`) — o mesmo critério de identidade
    de trial usado no banco (`trials.content_hash`).

    Args:
        video_path: Caminho do vídeo do trial.
        content_hash: Hash SHA-256 do vídeo (`VideoMetadata.content_hash`).
        frames: Quadros escolhidos por `sample_frames`.
        out_dir: Diretório base, normalmente `data/annotations`.

    Returns:
        O diretório do trial.
    """
    key = trial_key(content_hash)
    trial_dir = Path(out_dir) / key
    frames_dir = trial_dir / FRAMES_DIR
    frames_dir.mkdir(parents=True, exist_ok=True)

    for sampled in frames:
        image = read_frame(video_path, sampled.frame_index)
        target = frames_dir / frame_filename(sampled.frame_index)
        if not cv2.imwrite(str(target), image):
            raise OSError(f"Não foi possível gravar {target}")

    with (trial_dir / SAMPLING_CSV).open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            ["trial", "hash_video", "video", "quadro", "regiao_estimada", "x_px", "y_px"]
        )
        for sampled in frames:
            writer.writerow(
                [
                    key,
                    content_hash,
                    str(Path(video_path).resolve()),
                    sampled.frame_index,
                    sampled.region.value,
                    f"{sampled.x_px:.2f}",
                    f"{sampled.y_px:.2f}",
                ]
            )
    return trial_dir
