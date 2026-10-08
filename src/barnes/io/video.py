"""Leitura de vídeo de trial e extração dos metadados (US-01)."""

from __future__ import annotations

import hashlib
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import cv2
import numpy as np

SUPPORTED_EXTENSIONS = {".mp4"}
# 25%: vídeo real com B-frames mostrou um padrão normal e legítimo de
# intervalos alternando ~32ms/~48ms (desvio de ~20% em torno da mediana),
# sem que o fps seja de fato variável — a tolerância cobre esse jitter
# estrutural do codec sem deixar de pegar quebras reais maiores.
FPS_VARIABILITY_TOLERANCE = 0.25


class VideoLoadError(Exception):
    """Erro ao carregar um vídeo de trial (arquivo ausente, formato não suportado ou corrompido)."""


@dataclass(frozen=True)
class VideoMetadata:
    """Metadados extraídos de um vídeo de trial.

    Attributes:
        path: Caminho do arquivo de vídeo.
        width: Largura do quadro, em pixels.
        height: Altura do quadro, em pixels.
        frame_count: Número total de quadros, contado a partir da leitura
            (não do cabeçalho do contêiner).
        fps_declared: fps informado pelo cabeçalho do contêiner (RN01).
        fps_real: fps medido a partir dos carimbos de tempo dos quadros (RN02).
        duration_s: Duração total, em segundos, medida pelos carimbos de tempo.
        fps_is_variable: True se o intervalo entre quadros variar além de
            FPS_VARIABILITY_TOLERANCE (RN03).
        content_hash: Hash SHA-256 do conteúdo do arquivo (RN05).
        file_size_bytes: Tamanho do arquivo, em bytes — checagem barata de
            arquivo alterado no catálogo (US-27 RN04).
    """

    path: Path
    width: int
    height: int
    frame_count: int
    fps_declared: float
    fps_real: float
    duration_s: float
    fps_is_variable: bool
    content_hash: str
    file_size_bytes: int | None = None


def compute_content_hash(path: Path, chunk_size: int = 2**20) -> str:
    """Calcula o hash SHA-256 do conteúdo de um arquivo, em streaming.

    Args:
        path: Caminho do arquivo.
        chunk_size: Tamanho do bloco de leitura, em bytes.

    Returns:
        O hash em hexadecimal.
    """
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def real_fps_from_timestamps(timestamps_ms: Sequence[float]) -> float:
    """Calcula o fps real a partir dos carimbos de tempo dos quadros.

    Args:
        timestamps_ms: Carimbo de tempo (ms) de cada quadro, em ordem.

    Returns:
        O fps medido entre o primeiro e o último quadro.

    Raises:
        ValueError: Se houver menos de dois carimbos de tempo, ou se o
            intervalo medido entre eles não for positivo.
    """
    if len(timestamps_ms) < 2:
        raise ValueError("São necessários ao menos dois quadros para medir o fps.")
    elapsed_s = (timestamps_ms[-1] - timestamps_ms[0]) / 1000.0
    if elapsed_s <= 0:
        raise ValueError("Carimbos de tempo inválidos: duração medida não é positiva.")
    return (len(timestamps_ms) - 1) / elapsed_s


def is_fps_variable(
    timestamps_ms: Sequence[float], tolerance: float = FPS_VARIABILITY_TOLERANCE
) -> bool:
    """Detecta se o intervalo entre quadros varia além da tolerância (RN03).

    Args:
        timestamps_ms: Carimbo de tempo (ms) de cada quadro, em ordem.
        tolerance: Desvio relativo máximo aceito entre um intervalo e a
            mediana dos intervalos (ex.: 0.25 = 25%).

    Returns:
        True se algum intervalo entre quadros fugir da mediana além da
        tolerância informada.
    """
    if len(timestamps_ms) < 3:
        return False
    intervals = np.diff(np.asarray(timestamps_ms, dtype=float))
    median_interval = np.median(intervals)
    if median_interval <= 0:
        return False
    relative_deviation = np.abs(intervals - median_interval) / median_interval
    return bool((relative_deviation > tolerance).any())


def _validate_path(path: Path) -> None:
    """Valida existência e extensão antes de abrir o vídeo (Cenário 3)."""
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise VideoLoadError(f"Formato não suportado (apenas {supported} nesta versão): {path}")
    if not path.is_file():
        raise VideoLoadError(f"Arquivo não encontrado: {path}")


def load_trial_video(path: str | Path) -> VideoMetadata:
    """Carrega um vídeo de trial e extrai seus metadados (US-01).

    Args:
        path: Caminho do arquivo de vídeo (.mp4).

    Returns:
        Os metadados do vídeo, incluindo o hash de conteúdo.

    Raises:
        VideoLoadError: Se o arquivo não existir, tiver extensão não
            suportada, ou não puder ser lido (corrompido ou codec não
            suportado) — Cenário 3.
    """
    path = Path(path)
    _validate_path(path)

    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise VideoLoadError(f"Não foi possível abrir o vídeo (codec não suportado?): {path}")

        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps_declared = capture.get(cv2.CAP_PROP_FPS)
        if width <= 0 or height <= 0:
            raise VideoLoadError(f"Vídeo corrompido ou ilegível: {path}")

        timestamps_ms: list[float] = []
        while capture.grab():
            timestamps_ms.append(capture.get(cv2.CAP_PROP_POS_MSEC))

        if len(timestamps_ms) < 2:
            raise VideoLoadError(f"Vídeo corrompido ou ilegível: {path}")
    finally:
        capture.release()

    fps_real = real_fps_from_timestamps(timestamps_ms)
    fps_variable = is_fps_variable(timestamps_ms)
    if fps_variable:
        warnings.warn(
            f"fps variável detectado em {path.name} — usando fps medido pelos "
            "carimbos de tempo dos quadros.",
            stacklevel=2,
        )

    return VideoMetadata(
        path=path,
        width=width,
        height=height,
        frame_count=len(timestamps_ms),
        fps_declared=fps_declared,
        fps_real=fps_real,
        duration_s=timestamps_ms[-1] / 1000.0,
        fps_is_variable=fps_variable,
        content_hash=compute_content_hash(path),
        file_size_bytes=path.stat().st_size,
    )


class FileStatus(StrEnum):
    """Situação do arquivo de vídeo de um trial frente ao que foi catalogado (US-27 RN04)."""

    OK = "ok"  # no caminho registrado, com o mesmo hash
    PRESENTE = "presente"  # no caminho registrado; tamanho confere, hash não verificado
    ALTERADO = "alterado"  # no caminho registrado, mas com outro conteúdo
    MOVIDO = "movido"  # ausente do caminho registrado; mesmo conteúdo achado em outro lugar
    AUSENTE = "ausente"  # ausente do caminho registrado e não achado


@dataclass(frozen=True)
class FileCheck:
    """Resultado de `verify_video_file`.

    Attributes:
        status: Situação encontrada.
        path: Caminho registrado no catálogo.
        found_at: Onde o conteúdo com o hash esperado foi achado (só em MOVIDO).
        actual_hash: Hash do arquivo no caminho registrado, quando calculado.
    """

    status: FileStatus
    path: Path
    found_at: Path | None = None
    actual_hash: str | None = None

    @property
    def diverges(self) -> bool:
        """True se o arquivo não está, comprovadamente ou provavelmente, onde foi catalogado."""
        return self.status in (FileStatus.ALTERADO, FileStatus.MOVIDO, FileStatus.AUSENTE)

    def describe(self) -> str:
        """Mensagem para o operador, sem jargão de hash."""
        return {
            FileStatus.OK: "arquivo confere com o catalogado",
            FileStatus.PRESENTE: "arquivo presente (conteúdo não verificado)",
            FileStatus.ALTERADO: f"conteúdo de {self.path} difere do catalogado",
            FileStatus.MOVIDO: f"vídeo movido ou renomeado para {self.found_at}",
            FileStatus.AUSENTE: f"vídeo não encontrado em {self.path}",
        }[self.status]


def verify_video_file(
    path: str | Path,
    expected_hash: str,
    *,
    expected_size: int | None = None,
    verify_hash: bool = True,
    search_dirs: Sequence[str | Path] = (),
) -> FileCheck:
    """Confere se o vídeo catalogado continua no lugar e com o mesmo conteúdo (US-27 RN04).

    A identidade do trial é o conteúdo (`content_hash`, US-01 RN05), não o
    caminho: um arquivo renomeado ou movido continua sendo o mesmo trial,
    enquanto um arquivo substituído no mesmo caminho não é. Quando o arquivo
    sumiu do caminho registrado, procura `.mp4` com o mesmo hash na pasta
    original e em `search_dirs` (sem recursão), comparando primeiro o tamanho
    para só calcular hash de candidatos plausíveis.

    Args:
        path: Caminho registrado em `trials.filepath`.
        expected_hash: `trials.content_hash`.
        expected_size: `trials.file_size_bytes`, se conhecido — permite uma
            checagem barata quando `verify_hash=False`.
        verify_hash: False para checar só existência e tamanho (rápido, para
            listar o catálogo inteiro); o reprocessamento sempre usa True.
        search_dirs: Pastas extras onde procurar o arquivo movido.

    Returns:
        O resultado da verificação; nunca levanta por arquivo ausente.
    """
    path = Path(path)
    if path.is_file():
        if not verify_hash:
            if expected_size is not None and path.stat().st_size != expected_size:
                return FileCheck(FileStatus.ALTERADO, path)
            return FileCheck(FileStatus.PRESENTE, path)
        actual = compute_content_hash(path)
        status = FileStatus.OK if actual == expected_hash else FileStatus.ALTERADO
        return FileCheck(status, path, actual_hash=actual)

    for directory in dict.fromkeys(Path(d) for d in (path.parent, *search_dirs)):
        if not directory.is_dir():
            continue
        for candidate in sorted(directory.iterdir()):
            if candidate.suffix.lower() not in SUPPORTED_EXTENSIONS or not candidate.is_file():
                continue
            if expected_size is not None and candidate.stat().st_size != expected_size:
                continue
            if compute_content_hash(candidate) == expected_hash:
                return FileCheck(FileStatus.MOVIDO, path, found_at=candidate)
    return FileCheck(FileStatus.AUSENTE, path)


def read_frame(path: str | Path, frame_index: int = 0) -> np.ndarray:
    """Lê um quadro específico do vídeo.

    Usado para a pré-visualização interativa: o primeiro quadro pode estar
    obstruído (ex.: mão soltando o animal), então o operador precisa poder
    olhar outros quadros próximos.

    Args:
        path: Caminho do arquivo de vídeo.
        frame_index: Índice do quadro a ler (0 = primeiro).

    Returns:
        O quadro como array BGR (formato padrão do OpenCV).

    Raises:
        VideoLoadError: Se o índice não for um inteiro >= 0, se o vídeo não
            abrir, se o posicionamento no quadro falhar (para nunca devolver
            outro quadro em silêncio) ou se o quadro não puder ser lido (ex.:
            índice além do fim do vídeo).
    """
    if isinstance(frame_index, bool) or not isinstance(frame_index, int) or frame_index < 0:
        raise VideoLoadError("O índice do quadro deve ser um inteiro maior ou igual a zero.")
    path = Path(path)
    _validate_path(path)

    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise VideoLoadError(f"Não foi possível abrir o vídeo: {path}")
        if frame_index and not capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index):
            raise VideoLoadError(f"Não foi possível acessar o quadro {frame_index} de {path}")
        ok, frame = capture.read()
        if not ok or frame is None or frame.size == 0:
            raise VideoLoadError(f"Não foi possível ler o quadro {frame_index} de {path}")
        return frame
    except cv2.error as exc:
        raise VideoLoadError(f"Erro ao decodificar o vídeo {path}: {exc}") from exc
    finally:
        capture.release()
