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
from collections.abc import Callable, Iterator
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
    # Seek é aceitável aqui (diferente de `_iter_frames`): um quadro vizinho
    # no lugar do pedido não muda a mediana do fundo.
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


def _iter_frames(
    video_path: Path, start_frame: int, end_frame: int, wanted: Callable[[int], bool]
) -> Iterator[tuple[int, np.ndarray]]:
    """Percorre o vídeo em sequência desde o quadro 0, entregando os quadros pedidos.

    Nunca posiciona por `CAP_PROP_POS_FRAMES`: em H.264 com B-frames (caso dos
    vídeos do LNBio, ver US-01) o seek pode cair num quadro vizinho. A
    varredura e a exportação usam este mesmo caminho, então o PNG exportado é
    exatamente o quadro em que a posição foi estimada, e `quadro` é o índice
    real no vídeo — o que US-07/US-08 assumem ao voltar ao vídeo original.
    Os quadros antes de `start_frame` só são pulados com `grab()`, sem
    conversão de imagem.
    """
    capture = cv2.VideoCapture(str(video_path))
    try:
        if not capture.isOpened():
            raise VideoLoadError(f"Não foi possível abrir o vídeo: {video_path}")
        for index in range(end_frame + 1):
            if index >= start_frame and wanted(index):
                ok, frame = capture.read()
                if not ok:
                    return
                yield index, frame
            elif not capture.grab():
                return
    finally:
        capture.release()


def _scan(
    video_path: Path,
    geometry: MazeGeometry,
    protocol: AnnotationProtocol,
    background: np.ndarray,
    start_frame: int,
    end_frame: int,
    scan_step: int,
) -> tuple[list[SampledFrame], int]:
    candidates: list[SampledFrame] = []
    scanned = 0
    for index, frame in _iter_frames(
        video_path, start_frame, end_frame, lambda i: (i - start_frame) % scan_step == 0
    ):
        scanned += 1
        position = estimate_animal_position(frame, background, geometry)
        if position is not None:
            region = classify_region(*position, geometry, protocol.regions)
            candidates.append(SampledFrame(index, region, *position))
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


def check_previous_export(content_hash: str, out_dir: str | Path, *, overwrite: bool) -> list[Path]:
    """PNGs de uma amostragem anterior do mesmo trial, recusando-os sem `overwrite`.

    Reamostrar reescreve `amostragem.csv`, mas PNGs da rodada anterior que
    não forem sorteados de novo sobrariam em `quadros/` e poderiam ser
    importados no SLEAP como se fossem do conjunto atual. Como podem ser
    quadros já anotados, apagá-los exige pedido explícito.

    Args:
        content_hash: Hash SHA-256 do vídeo do trial.
        out_dir: Diretório base da exportação.
        overwrite: Se `True`, os PNGs anteriores são só listados (para que
            `export_frames` os apague); se `False`, a existência deles é erro.

    Returns:
        Os PNGs anteriores (vazio se o trial nunca foi amostrado ali).

    Raises:
        FileExistsError: Se houver PNGs anteriores e `overwrite` for `False`.
    """
    frames_dir = Path(out_dir) / trial_key(content_hash) / FRAMES_DIR
    previous = sorted(frames_dir.glob("quadro_*.png")) if frames_dir.is_dir() else []
    if previous and not overwrite:
        raise FileExistsError(
            f"{frames_dir} já tem {len(previous)} quadro(s) de uma amostragem anterior deste "
            "trial, que podem já ter sido anotados. Use --overwrite para apagá-los e reamostrar."
        )
    return previous


def export_frames(
    video_path: str | Path,
    content_hash: str,
    frames: tuple[SampledFrame, ...] | list[SampledFrame],
    out_dir: str | Path,
    *,
    maze_config_id: int,
    overwrite: bool = False,
) -> Path:
    """Grava os quadros escolhidos como PNG, prontos para importar no SLEAP.

    Estrutura: `<out_dir>/<trial>/quadros/quadro_NNNNNN.png` mais
    `<out_dir>/<trial>/amostragem.csv`, em que `<trial>` é a chave curta do
    hash de conteúdo do vídeo (`trial_key`) — o mesmo critério de identidade
    de trial usado no banco (`trials.content_hash`). Os quadros são lidos na
    mesma passada sequencial da varredura (`_iter_frames`), sem seek.

    Args:
        video_path: Caminho do vídeo do trial.
        content_hash: Hash SHA-256 do vídeo (`VideoMetadata.content_hash`).
        frames: Quadros escolhidos por `sample_frames`.
        out_dir: Diretório base, normalmente `data/annotations`.
        maze_config_id: Montagem usada na amostragem. Fica registrada no CSV
            para que a contagem por região (`barnes pose report`) use a
            geometria do próprio trial — trials de dias diferentes podem ter
            a câmera deslocada e, portanto, outra montagem.
        overwrite: Apaga os PNGs de uma amostragem anterior do mesmo trial
            em vez de recusar (ver `check_previous_export`).

    Returns:
        O diretório do trial.

    Raises:
        FileExistsError: Se já houver PNGs deste trial e `overwrite` for `False`.
        VideoLoadError: Se o vídeo acabar antes de algum quadro escolhido.
    """
    key = trial_key(content_hash)
    trial_dir = Path(out_dir) / key
    frames_dir = trial_dir / FRAMES_DIR
    for previous in check_previous_export(content_hash, out_dir, overwrite=overwrite):
        previous.unlink()
    frames_dir.mkdir(parents=True, exist_ok=True)

    wanted = {sampled.frame_index for sampled in frames}
    written = set()
    if wanted:
        for index, image in _iter_frames(
            Path(video_path), min(wanted), max(wanted), wanted.__contains__
        ):
            target = frames_dir / frame_filename(index)
            if not cv2.imwrite(str(target), image):
                raise OSError(f"Não foi possível gravar {target}")
            written.add(index)
    if written != wanted:
        missing = ", ".join(str(i) for i in sorted(wanted - written))
        raise VideoLoadError(f"O vídeo {video_path} acabou antes do(s) quadro(s) {missing}.")

    with (trial_dir / SAMPLING_CSV).open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "trial",
                "hash_video",
                "video",
                "maze_config_id",
                "quadro",
                "regiao_estimada",
                "x_px",
                "y_px",
            ]
        )
        for sampled in frames:
            writer.writerow(
                [
                    key,
                    content_hash,
                    str(Path(video_path).resolve()),
                    maze_config_id,
                    sampled.frame_index,
                    sampled.region.value,
                    f"{sampled.x_px:.2f}",
                    f"{sampled.y_px:.2f}",
                ]
            )
    return trial_dir


def read_sampled_maze_config(trial_dir: str | Path) -> int | None:
    """Montagem registrada no `amostragem.csv` de um trial por `export_frames`.

    Args:
        trial_dir: Diretório do trial (`<out_dir>/<trial>`).

    Returns:
        O `maze_config_id`, ou `None` se não houver `amostragem.csv`, se ele
        estiver vazio ou se for anterior a este registro (sem a coluna).

    Raises:
        ValueError: Se o valor não for inteiro ou se o CSV registrar mais de
            uma montagem para o mesmo trial.
    """
    path = Path(trial_dir) / SAMPLING_CSV
    if not path.is_file():
        return None
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if "maze_config_id" not in (reader.fieldnames or []):
            return None
        values = {row["maze_config_id"] for row in reader}
    if not values:
        return None
    if len(values) > 1:
        raise ValueError(f"{path} registra mais de uma montagem: {', '.join(sorted(values))}.")
    (value,) = values
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"maze_config_id inválido em {path}: '{value}'.") from exc
