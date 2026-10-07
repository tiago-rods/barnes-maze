"""Pacotes locais, imutáveis e verificáveis de quadros rotulados (US-07)."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np

from barnes.pose.annotations import (
    FRAMES_DIR,
    KEYPOINTS,
    frame_filename,
    read_annotations_csv,
    validate_complete,
)
from barnes.pose.sampling import read_sampled_maze_config
from barnes.pose.split import SETS, ManifestRow, check_no_leakage, read_manifest, write_manifest


class DatasetError(ValueError):
    """Dados não permitem treino reproduzível sem vazamento."""


def file_sha256(path: str | Path) -> str:
    """Calcula SHA-256 sem carregar arquivos grandes na memória."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: dict) -> None:
    """Grava JSON estrito, com substituição atômica de um registro anterior."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def contained_path(root: Path, relative: str) -> Path:
    """Resolve um artefato local e rejeita referências fora do pacote."""
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise DatasetError(f"Caminho fora do pacote: {relative}")
    return path


def _identity(manifest: dict) -> str:
    content = {
        key: manifest[key] for key in ("schema_version", "maze_config_id", "keypoints", "frames")
    }
    encoded = json.dumps(content, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "dataset-" + hashlib.sha256(encoded.encode()).hexdigest()


def export_slp(frames: list[dict], root: Path, output: Path) -> None:
    """Exporta apenas PNGs rotulados em SLP autocontido, sem vídeos originais.

    A ordem dos quadros por trial no SLP é a ordem de ``frames``; o manifesto
    preserva o índice do vídeo original. Embutir os PNGs permite mover o pacote.
    """
    try:
        import sleap_io as sio
    except ImportError as exc:
        raise ImportError("Preparar .slp requer: uv sync --extra anotacao") from exc
    skeleton = sio.Skeleton(
        nodes=list(KEYPOINTS), edges=[(KEYPOINTS[0], KEYPOINTS[1]), (KEYPOINTS[1], KEYPOINTS[2])]
    )
    labeled = []
    for trial in sorted({frame["trial"] for frame in frames}):
        selected = [frame for frame in frames if frame["trial"] == trial]
        video = sio.Video.from_filename([str(root / frame["image_path"]) for frame in selected])
        for index, frame in enumerate(selected):
            instance = sio.Instance.from_numpy(np.asarray(frame["points"]), skeleton=skeleton)
            labeled.append(sio.LabeledFrame(video=video, frame_idx=index, instances=[instance]))
    sio.save_slp(sio.Labels(labeled_frames=labeled), str(output), embed=True)


def prepare_dataset(
    annotations_path: str | Path,
    split_path: str | Path,
    frames_dir: str | Path,
    output_root: str | Path,
    maze_config_id: int,
    *,
    exporter: Callable[[list[dict], Path, Path], None] | None = None,
) -> Path:
    """Congela a divisão US-06 e os PNGs; retorna diretório com versão por conteúdo.

    Exige três subconjuntos não vazios, uma montagem e correspondência exata
    entre anotações e divisão. Dados originais não são alterados. Uma versão
    existente é verificada antes de ser reutilizada; nunca é sobrescrita.
    """
    if (
        isinstance(maze_config_id, bool)
        or not isinstance(maze_config_id, int)
        or maze_config_id < 1
    ):
        raise DatasetError("maze_config_id deve ser um inteiro positivo.")
    annotations = read_annotations_csv(annotations_path)
    validate_complete(annotations)
    rows = read_manifest(split_path)
    check_no_leakage(rows)
    keys = [(row.trial, row.frame_index) for row in rows]
    if len(keys) != len(set(keys)):
        raise DatasetError("A divisão contém quadros duplicados.")
    annotated = {(frame.trial, frame.frame_index) for frame in annotations}
    if set(keys) != annotated:
        raise DatasetError("Anotações e divisão devem conter exatamente os mesmos quadros.")
    if {row.subset for row in rows} != set(SETS):
        raise DatasetError("Treino, validação e teste devem conter pelo menos um trial cada.")
    subsets = {(row.trial, row.frame_index): row.subset for row in rows}
    source = Path(frames_dir).resolve()
    records = []
    sources = {}
    image_subsets: dict[str, str] = {}
    for trial in sorted({frame.trial for frame in annotations}):
        if not re.fullmatch(r"[a-f0-9]{12}", trial):
            raise DatasetError(f"Chave de trial inválida: {trial}; use os hashes de US-06.")
        registered = read_sampled_maze_config(source / trial)
        if registered != maze_config_id:
            raise DatasetError(
                f"Trial {trial}: montagem de amostragem {registered}, esperada {maze_config_id}."
            )
    for frame in sorted(annotations, key=lambda value: (value.trial, value.frame_index)):
        if frame.frame_index < 0:
            raise DatasetError("Índice de quadro negativo.")
        relative = Path(frame.trial) / FRAMES_DIR / frame_filename(frame.frame_index)
        original = contained_path(source, str(relative))
        raw = original.read_bytes()
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise DatasetError(f"PNG inválido: {original}")
        height, width = image.shape[:2]
        if any(not (0 <= x < width and 0 <= y < height) for x, y in frame.points):
            raise DatasetError(
                f"Ponto fora da imagem em {frame.trial}, quadro {frame.frame_index}."
            )
        digest = hashlib.sha256(raw).hexdigest()
        subset = subsets[(frame.trial, frame.frame_index)]
        previous = image_subsets.setdefault(digest, subset)
        if previous != subset:
            raise DatasetError("PNG idêntico em subconjuntos diferentes: possível vazamento.")
        image_path = (Path("frames") / relative).as_posix()
        records.append(
            {
                "trial": frame.trial,
                "frame_index": frame.frame_index,
                "subset": subset,
                "points": frame.points,
                "image_path": image_path,
                "image_sha256": digest,
                "width": width,
                "height": height,
            }
        )
        sources[image_path] = original
    manifest = {
        "schema_version": 1,
        "maze_config_id": maze_config_id,
        "keypoints": list(KEYPOINTS),
        "frames": records,
    }
    manifest["dataset_id"] = _identity(manifest)
    target = Path(output_root).resolve() / manifest["dataset_id"]
    if target.exists():
        load_dataset_manifest(target)
        return target
    target.mkdir(parents=True)
    manifest.update(
        status="preparing", created_at=datetime.now(UTC).isoformat(), subsets={}, artifacts={}
    )
    write_json(target / "manifest.json", manifest)
    try:
        for record in records:
            destination = target / record["image_path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(sources[record["image_path"]], destination)
            if file_sha256(destination) != record["image_sha256"]:
                raise DatasetError("PNG mudou durante a preparação; gere uma nova versão.")
        # US-06 costuma usar duas casas decimais; preserve também CSVs com
        # precisão maior para não alterar rótulos durante o congelamento.
        with (target / "anotacoes.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["trial", "quadro"] +
                            [f"{name}_{axis}" for name in KEYPOINTS for axis in ("x", "y")])
            for frame in sorted(annotations, key=lambda item: (item.trial, item.frame_index)):
                writer.writerow([frame.trial, frame.frame_index,
                                 *(value for point in frame.points for value in point)])
        write_manifest(
            sorted(rows, key=lambda row: (row.trial, row.frame_index)), target / "divisao.csv"
        )
        for subset in SETS:
            selected = [frame for frame in records if frame["subset"] == subset]
            (exporter or export_slp)(selected, target, target / f"{subset}.pkg.slp")
            manifest["subsets"][subset] = {
                "frames": len(selected),
                "trials": len({frame["trial"] for frame in selected}),
            }
        manifest["artifacts"] = {
            path.relative_to(target).as_posix(): file_sha256(path)
            for path in sorted(target.rglob("*"))
            if path.is_file() and path.name != "manifest.json"
        }
        manifest["status"] = "ready"
    except BaseException as exc:
        manifest.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        write_json(target / "manifest.json", manifest)
        raise
    write_json(target / "manifest.json", manifest)
    return target


def load_dataset_manifest(dataset_dir: str | Path, verify: bool = True) -> dict:
    """Lê a versão congelada e detecta alterações em rótulos, imagens e SLPs."""
    root = Path(dataset_dir)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "ready" or manifest.get("schema_version") != 1:
        raise DatasetError("Pacote incompleto ou versão de manifesto não suportada.")
    if _identity(manifest) != manifest.get("dataset_id"):
        raise DatasetError("Identificador do conjunto difere de seu conteúdo.")
    if manifest.get("keypoints") != list(KEYPOINTS):
        raise DatasetError("Esqueleto do conjunto incompatível com os três pontos de Barnes.")
    counts = Counter(frame["subset"] for frame in manifest["frames"])
    if set(counts) != set(SETS):
        raise DatasetError("O conjunto precisa de treino, validação e teste.")
    rows = [ManifestRow(frame["trial"], frame["frame_index"], frame["subset"])
            for frame in manifest["frames"]]
    check_no_leakage(rows)
    keys = [(row.trial, row.frame_index) for row in rows]
    if len(keys) != len(set(keys)):
        raise DatasetError("Manifesto contém quadros duplicados.")
    for subset in SETS:
        expected = {"frames": counts[subset],
                    "trials": len({row.trial for row in rows if row.subset == subset})}
        if manifest.get("subsets", {}).get(subset) != expected:
            raise DatasetError("Contagem dos subconjuntos difere dos quadros registrados.")
    required = {"anotacoes.csv", "divisao.csv", *(f"{name}.pkg.slp" for name in SETS)}
    required.update(frame["image_path"] for frame in manifest["frames"])
    if not required.issubset(manifest.get("artifacts", {})):
        raise DatasetError("Manifesto não registra todos os artefatos obrigatórios.")
    if verify:
        for relative, expected in manifest["artifacts"].items():
            path = contained_path(root, relative)
            if not path.is_file() or file_sha256(path) != expected:
                raise DatasetError(f"Artefato ausente ou alterado: {relative}")
        for frame in manifest["frames"]:
            if manifest["artifacts"][frame["image_path"]] != frame["image_sha256"]:
                raise DatasetError("Hash de imagem inconsistente no manifesto.")
        annotations = read_annotations_csv(root / "anotacoes.csv")
        validate_complete(annotations)
        recorded = {(frame["trial"], frame["frame_index"]): frame["points"]
                    for frame in manifest["frames"]}
        if len(annotations) != len(recorded) or any(
            [list(point) for point in frame.points] != recorded.get((frame.trial, frame.frame_index))
            for frame in annotations
        ):
            raise DatasetError("Rótulos congelados diferem do manifesto.")
        frozen_split = read_manifest(root / "divisao.csv")
        if sorted(frozen_split, key=lambda row: (row.trial, row.frame_index)) != sorted(
            rows, key=lambda row: (row.trial, row.frame_index)
        ):
            raise DatasetError("Divisão congelada difere do manifesto.")
    return manifest
