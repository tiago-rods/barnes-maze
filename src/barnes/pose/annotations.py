"""Conjunto anotado de pose: formato interno, validação e importação do SLEAP (US-06).

O resto do pipeline lê só o formato interno (`anotacoes.csv`), não o arquivo
da ferramenta de anotação. A anotação é feita na interface do SLEAP (RN05),
mas a abordagem de pose ainda está em revisão no Sprint 1 (RN07) — se a
ferramenta mudar, muda só o conversor (`from_slp`), não o resto.
"""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path

from barnes.io.video import compute_content_hash

# Ordem fixa dos pontos (RN01). É também a ordem dos nós do esqueleto no SLEAP.
KEYPOINTS = ("focinho", "centro_corpo", "base_cauda")

# Caracteres do hash SHA-256 usados como chave curta do trial em nomes de
# pasta e CSV. 12 hex = 48 bits: colisão desprezível para dezenas de trials.
TRIAL_KEY_LENGTH = 12

FRAMES_DIR = "quadros"
ANNOTATIONS_CSV = "anotacoes.csv"

_IMAGE_PATH = re.compile(r"([^/\\]+)[/\\]" + FRAMES_DIR + r"[/\\]quadro_(\d+)\.png$")


class AnnotationError(ValueError):
    """Conjunto anotado inválido: ponto faltando, quadro duplicado ou esqueleto errado."""


def trial_key(content_hash: str) -> str:
    """Chave curta de um trial, derivada do hash de conteúdo do vídeo.

    O trial é identificado pelo conteúdo, não pelo nome do arquivo — mesma
    regra de `trials.content_hash` no banco —, para que o mesmo vídeo com
    outro nome não escape da verificação de vazamento entre conjuntos.
    """
    return content_hash[:TRIAL_KEY_LENGTH]


def frame_filename(frame_index: int) -> str:
    """Nome do PNG exportado para anotação; `from_slp` recupera o índice dele."""
    return f"quadro_{frame_index:06d}.png"


@dataclass(frozen=True)
class AnnotatedFrame:
    """Um quadro anotado.

    Attributes:
        trial: Chave do trial (`trial_key`).
        frame_index: Índice do quadro no vídeo original.
        points: `(x_px, y_px)` de cada ponto, na ordem de `KEYPOINTS`.
            Ponto não marcado vem como `(nan, nan)`.
    """

    trial: str
    frame_index: int
    points: tuple[tuple[float, float], ...]

    def point(self, name: str) -> tuple[float, float]:
        """Coordenadas de um ponto pelo nome (ex.: `"centro_corpo"`)."""
        return self.points[KEYPOINTS.index(name)]

    def missing(self) -> list[str]:
        """Nomes dos pontos não marcados neste quadro."""
        return [
            name
            for name, (x, y) in zip(KEYPOINTS, self.points, strict=True)
            if not (math.isfinite(x) and math.isfinite(y))
        ]


def _csv_header() -> list[str]:
    return ["trial", "quadro"] + [f"{name}_{axis}" for name in KEYPOINTS for axis in ("x", "y")]


def write_annotations_csv(frames: list[AnnotatedFrame], path: str | Path) -> Path:
    """Grava o conjunto anotado no formato interno, ordenado por trial e quadro."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(_csv_header())
        for frame in sorted(frames, key=lambda f: (f.trial, f.frame_index)):
            coords = [
                "" if not math.isfinite(value) else f"{value:.2f}"
                for point in frame.points
                for value in point
            ]
            writer.writerow([frame.trial, frame.frame_index, *coords])
    return path


def read_annotations_csv(path: str | Path) -> list[AnnotatedFrame]:
    """Lê o conjunto anotado do formato interno.

    Raises:
        AnnotationError: Se faltar coluna ou algum valor não for numérico.
    """
    path = Path(path)
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        missing_columns = set(_csv_header()) - set(reader.fieldnames or [])
        if missing_columns:
            raise AnnotationError(
                f"{path.name} sem as colunas: {', '.join(sorted(missing_columns))}."
            )
        frames = []
        for row in reader:
            try:
                points = tuple(
                    (
                        float(row[f"{name}_x"] or "nan"),
                        float(row[f"{name}_y"] or "nan"),
                    )
                    for name in KEYPOINTS
                )
                frames.append(AnnotatedFrame(row["trial"], int(row["quadro"]), points))
            except ValueError as exc:
                raise AnnotationError(
                    f"Valor inválido na linha {reader.line_num} de {path.name}."
                ) from exc
    return frames


def validate_complete(frames: list[AnnotatedFrame]) -> None:
    """Exige os três pontos em todo quadro anotado e nenhum quadro repetido (Cenário 1).

    Raises:
        AnnotationError: Listando os quadros com ponto faltando ou duplicados.
    """
    if not frames:
        raise AnnotationError("O conjunto anotado está vazio.")
    problems = []
    seen: set[tuple[str, int]] = set()
    for frame in frames:
        key = (frame.trial, frame.frame_index)
        if key in seen:
            problems.append(f"trial {frame.trial}, quadro {frame.frame_index}: duplicado")
        seen.add(key)
        missing = frame.missing()
        if missing:
            problems.append(
                f"trial {frame.trial}, quadro {frame.frame_index}: falta {', '.join(missing)}"
            )
    if problems:
        shown = "\n  ".join(problems[:20])
        extra = f"\n  ... e mais {len(problems) - 20}" if len(problems) > 20 else ""
        raise AnnotationError(f"Conjunto anotado incompleto:\n  {shown}{extra}")


def _locate(filename: str | list[str], frame_idx: int, hashes: dict[str, str]) -> tuple[str, int]:
    """Converte a referência de quadro do SLEAP em `(trial, índice no vídeo original)`."""
    if isinstance(filename, list | tuple):
        image = str(filename[frame_idx])
        match = _IMAGE_PATH.search(image)
        if match is None:
            raise AnnotationError(
                f"Imagem fora do padrão <trial>/{FRAMES_DIR}/quadro_NNNNNN.png: {image}. "
                "Importe no SLEAP os PNGs gerados por `barnes pose sample`."
            )
        return match.group(1), int(match.group(2))

    video = Path(filename)
    if video.suffix.lower() == ".slp":
        # Projeto salvo com imagens embutidas (ex.: `.pkg.slp`): o "vídeo" é o
        # próprio .slp, e o hash dele viraria uma chave de trial falsa — dois
        # trials no mesmo pacote passariam por um só na verificação de vazamento.
        raise AnnotationError(
            f"{video.name} tem as imagens embutidas no próprio .slp, então não dá para saber "
            "de que trial vem cada quadro. Salve o projeto no SLEAP como .slp comum (sem "
            "embutir imagens), apontando para os PNGs de `barnes pose sample`."
        )
    if str(video) not in hashes:
        if not video.is_file():
            raise AnnotationError(f"Vídeo referenciado pelo projeto SLEAP não encontrado: {video}")
        hashes[str(video)] = trial_key(compute_content_hash(video))
    return hashes[str(video)], frame_idx


def from_slp(path: str | Path) -> list[AnnotatedFrame]:
    """Converte um projeto de anotação do SLEAP (`.slp`) para o formato interno.

    Lê só as instâncias marcadas por pessoa (não predições). Aceita quadros
    importados como imagens geradas por `barnes pose sample` — o trial e o
    índice do quadro vêm do caminho do PNG — ou direto do vídeo `.mp4`,
    caso em que o trial vem do hash do vídeo.

    Requer o extra opcional `anotacao` (`sleap-io`, BSD-3), que lê o arquivo
    sem instalar o SLEAP completo nem CUDA.

    Raises:
        AnnotationError: Se o esqueleto não tiver os três pontos, se houver
            mais de um animal anotado num quadro, ou se a origem do quadro
            não puder ser identificada (inclusive projeto com imagens
            embutidas, `.pkg.slp`).
        ImportError: Se `sleap-io` não estiver instalado.
    """
    try:
        import sleap_io
    except ImportError as exc:
        raise ImportError(
            "Ler arquivos .slp requer o extra 'anotacao': uv sync --extra anotacao"
        ) from exc

    # Só os nomes dos arquivos interessam: não abre vídeo nem imagem, então o .slp
    # pode vir da máquina de outro integrante, com caminhos que não existem aqui.
    labels = sleap_io.load_slp(str(path), open_videos=False)
    hashes: dict[str, str] = {}
    frames = []
    for labeled in labels.labeled_frames:
        instances = labeled.user_instances
        if not instances:
            continue
        if len(instances) > 1:
            raise AnnotationError(
                f"Quadro {labeled.frame_idx} tem {len(instances)} animais anotados; "
                "o protocolo é de animal único."
            )
        instance = instances[0]
        names = list(instance.skeleton.node_names)
        absent = [name for name in KEYPOINTS if name not in names]
        if absent:
            raise AnnotationError(
                f"Esqueleto do SLEAP sem os nós {', '.join(absent)}; "
                f"use exatamente: {', '.join(KEYPOINTS)}."
            )
        coords = instance.numpy()
        points = tuple(
            (float(coords[names.index(name)][0]), float(coords[names.index(name)][1]))
            for name in KEYPOINTS
        )
        trial, frame_index = _locate(labeled.video.filename, labeled.frame_idx, hashes)
        frames.append(AnnotatedFrame(trial, frame_index, points))
    return frames
