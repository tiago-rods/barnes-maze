"""Inferência SLEAP local em lotes, com identidade, intervalo e tempo auditáveis."""

from __future__ import annotations

import csv
import importlib.metadata
import json
import math
import subprocess
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np

from barnes.io.trim import TrialInterval
from barnes.pose.annotations import KEYPOINTS, AnnotatedFrame, trial_key
from barnes.pose.dataset import contained_path, file_sha256, load_dataset_manifest, write_json
from barnes.pose.offline import offline_network
from barnes.pose.training import (
    SLEAP_IO_VERSION,
    SLEAP_NN_VERSION,
    environment_record,
    load_model_manifest,
)


class InferenceError(ValueError):
    """Modelo, vídeo ou saída incompatível com a inferência de animal único."""

    def __init__(self, message: str, *, run_dir: Path | None = None):
        super().__init__(message)
        self.run_dir = run_dir


class SleapBackend:
    """Adaptador da API pública SLEAP-NN 0.3.1, sem downloads automáticos.

    A decodificação pertence ao Barnes: a leitura sequencial evita o desvio de
    índices causado por seek em vídeos com B-frames. A API recebe só pixels,
    nunca as coordenadas anotadas do conjunto de teste.
    """

    def __init__(self, model_dir: Path, *, device: str = "cpu", batch_size: int = 4):
        for package, required in (("sleap-nn", SLEAP_NN_VERSION), ("sleap-io", SLEAP_IO_VERSION)):
            try:
                installed = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError as exc:
                raise InferenceError(
                    "Instale o ambiente de pose antes: uv sync --extra pose"
                ) from exc
            if installed != required:
                raise InferenceError(
                    f"Inferência exige {package}=={required}; instalado {installed}."
                )
        from sleap_nn.inference.predictor import Predictor
        from sleap_nn.inference.providers import NumpyProvider

        self.provider = NumpyProvider
        self.predictor = Predictor.from_model_paths(
            [str(model_dir / "sleap")],
            device=device,
            batch_size=batch_size,
            # Preserva todos os picos; qualidade é avaliada, não filtrada silenciosamente.
            peak_threshold=0.0,
        )
        names = list(self.predictor.skeleton.node_names)
        if len(names) != len(KEYPOINTS) or set(names) != set(KEYPOINTS):
            raise InferenceError("O esqueleto carregado não contém exatamente os três pontos.")
        self.node_order = [names.index(name) for name in KEYPOINTS]

    def predict(self, images: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Recebe RGB uint8 (B,H,W,C); retorna coordenadas originais e confiança."""
        outputs = self.predictor.predict(
            self.provider(images, batch_size=len(images)), make_labels=False
        )
        coords, scores = [], []
        for output in outputs:
            values = output.numpy()
            points = values.get("pred_keypoints")
            peaks = values.get("pred_peak_values")
            if points is None or points.ndim != 4 or points.shape[1:] != (1, 3, 2):
                raise InferenceError("SLEAP retornou formato diferente de um animal/três pontos.")
            points = points[:, 0, self.node_order, :].copy()
            confidence = (
                np.full(points.shape[:2], np.nan)
                if peaks is None
                else peaks[:, 0, self.node_order].copy()
            )
            valid = values.get("instance_valid")
            if valid is not None:
                invalid = ~np.asarray(valid[:, 0], dtype=bool)
                points[invalid] = np.nan
                confidence[invalid] = np.nan
            coords.append(points)
            scores.append(confidence)
        if not coords:
            raise InferenceError("SLEAP não retornou os quadros solicitados.")
        return np.concatenate(coords), np.concatenate(scores)


def _options(device: str, batch_size: int) -> None:
    if not isinstance(device, str) or (
        device != "cpu" and not (device.startswith("cuda:") and device[5:].isdigit())
    ):
        raise InferenceError("Use --device cpu ou cuda:N.")
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
        raise InferenceError("batch_size deve ser inteiro positivo.")


def _predict(backend, images: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    points, scores = backend.predict(np.stack(images))
    points, scores = (
        np.array(points, dtype=float, copy=True),
        np.array(scores, dtype=float, copy=True),
    )
    if points.shape != (len(images), 3, 2) or scores.shape != (len(images), 3):
        raise InferenceError("Quantidade/formato de predições não corresponde aos quadros.")
    # NaNs preservam ausência, nunca viram (0,0) nem somem do relatório.
    points[~np.isfinite(points)] = np.nan
    scores[~np.isfinite(scores)] = np.nan
    return points, scores


def _sequential_frames(video: Path, start: int, end: int) -> Iterator[tuple[int, np.ndarray]]:
    capture = cv2.VideoCapture(str(video))
    try:
        if not capture.isOpened():
            raise InferenceError(f"Não foi possível abrir o vídeo local: {video}")
        for index in range(end + 1):
            ok, image = capture.read()
            if not ok:
                raise InferenceError(f"Vídeo terminou/falhou no quadro {index}, antes de {end}.")
            if index >= start:
                yield index, cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    finally:
        capture.release()


def _source_record() -> dict:
    """Identifica o código executado, inclusive alterações ainda sem commit."""
    package = Path(__file__).resolve().parents[1]
    source = {
        "python_files_sha256": {
            path.relative_to(package).as_posix(): file_sha256(path)
            for path in sorted(package.rglob("*.py"))
        },
        "git_commit": None,
        "git_dirty": None,
    }
    try:
        source["git_commit"] = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=package,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout.strip()
        source["git_dirty"] = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=package,
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            ).stdout.strip()
        )
    except (OSError, subprocess.SubprocessError):
        pass
    return source


def _new_record(
    output_root: Path, model: dict, kind: str, device: str, batch_size: int
) -> tuple[Path, dict]:
    run_dir = output_root.resolve() / f"{kind}-{uuid.uuid4().hex}"
    run_dir.mkdir(parents=True, exist_ok=False)
    record = {
        "schema_version": 1,
        "status": "running",
        "kind": kind,
        "model_id": model["model_id"],
        "maze_config_id": model["maze_config_id"],
        "dataset_id": model["dataset_id"],
        "model_artifacts": model["artifacts"],
        "started_at": datetime.now(UTC).isoformat(),
        "environment": environment_record(),
        "source": _source_record(),
        "device": device,
        "batch_size": batch_size,
        "peak_threshold": 0.0,
        "network_policy": "python_loopback_only",
        "physical_network_disconnection_verified": False,
        "data_uploaded": False,
    }
    write_json(run_dir / "execucao.json", record)
    return run_dir, record


def _finish(run_dir: Path, record: dict, started: float) -> None:
    record["artifacts"] = {
        p.name: file_sha256(p)
        for p in run_dir.iterdir()
        if p.is_file() and p.name != "execucao.json"
    }
    record["duration_seconds"] = time.perf_counter() - started
    record["finished_at"] = datetime.now(UTC).isoformat()
    record["duration_scope"] = (
        "verificação das entradas, carregamento do backend, decodificação, inferência, "
        "escrita do CSV e hashes de saída; exclui escrita final deste registro e PostgreSQL"
    )
    write_json(run_dir / "execucao.json", record)


def _load_model(model_dir: Path) -> dict:
    try:
        return load_model_manifest(model_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise InferenceError(f"Modelo local inválido: {exc}") from exc


def _load_dataset(dataset_dir: Path) -> dict:
    try:
        return load_dataset_manifest(dataset_dir)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise InferenceError(f"Conjunto local inválido: {exc}") from exc


def load_inference_record(run_dir: str | Path, verify: bool = True) -> dict:
    """Lê registro concluído ou falho e verifica hashes dos artefatos locais.

    Uma execução falha pode não ter CSV ou tê-lo parcial; ``status`` deve ser
    consultado antes de consumir as predições. ``verify=False`` ignora somente
    os hashes, não a estrutura nem a contenção dos caminhos no diretório.
    """
    run_dir = Path(run_dir).resolve()
    try:
        record = json.loads((run_dir / "execucao.json").read_text(encoding="utf-8"))
        if (
            not isinstance(record, dict)
            or record.get("schema_version") != 1
            or record.get("status") not in {"completed", "failed"}
            or record.get("kind") not in {"inferencia", "teste"}
        ):
            raise ValueError("Execução incompleta ou estrutura incompatível.")
        duration = record.get("duration_seconds")
        if (
            isinstance(duration, bool)
            or not isinstance(duration, int | float)
            or not math.isfinite(duration)
            or duration < 0
        ):
            raise ValueError("Duração de inferência inválida.")
        if not all(record.get(key) for key in ("model_id", "dataset_id", "maze_config_id")):
            raise ValueError("Registro sem identidade de modelo, conjunto ou montagem.")
        artifacts = record.get("artifacts")
        if not isinstance(artifacts, dict):
            raise TypeError("Registro sem hashes de artefatos.")
        required = "pose.csv" if record["kind"] == "inferencia" else "predicoes.csv"
        if record["status"] == "completed" and required not in artifacts:
            raise ValueError(f"Execução concluída sem artefato obrigatório: {required}.")
        for relative, expected in artifacts.items():
            path = contained_path(run_dir, relative)
            if verify and (not path.is_file() or file_sha256(path) != expected):
                raise ValueError(f"Artefato de inferência ausente ou alterado: {relative}.")
        return record
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise InferenceError(f"Registro de inferência inválido: {exc}", run_dir=run_dir) from exc


def infer_trial(
    model_dir: str | Path,
    video: str | Path,
    output_root: str | Path,
    *,
    trial_id: int,
    maze_config_id: int,
    interval: TrialInterval,
    expected_content_hash: str,
    fps: float,
    frame_count: int,
    width: int,
    height: int,
    device: str = "cpu",
    batch_size: int = 4,
    backend_factory: Callable | None = None,
) -> Path:
    """Processa somente o intervalo cadastrado e escreve CSV + registro local.

    Tempo inclui verificação do vídeo, carregamento do modelo, decodificação,
    inferência, escrita do CSV e hashes de saída; exclui escrita final do
    registro e gravação posterior no PostgreSQL.
    O CSV é pose bruta em pixels, não uma trajetória corrigida da futura US-09.
    ``backend_factory`` é um ponto de injeção para testes; seu uso fica explícito
    no registro e não constitui validação do modelo SLEAP real.
    """
    _options(device, batch_size)
    model_dir, video = Path(model_dir).resolve(), Path(video).resolve()
    model = _load_model(model_dir)
    if model["maze_config_id"] != maze_config_id:
        raise InferenceError("Montagem do modelo difere da montagem registrada no trial.")
    for name, value in {
        "trial_id": trial_id,
        "maze_config_id": maze_config_id,
        "frame_count": frame_count,
        "width": width,
        "height": height,
    }.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise InferenceError(f"{name} deve ser um inteiro positivo cadastrado.")
    if (
        not isinstance(interval, TrialInterval)
        or any(
            isinstance(index, bool) or not isinstance(index, int)
            for index in (interval.start_frame, interval.end_frame)
        )
        or not 0 <= interval.start_frame < frame_count
        or not interval.start_frame <= interval.end_frame <= frame_count
    ):
        raise InferenceError("Trial exige intervalo útil válido e cadastrado (US-03).")
    if (
        isinstance(fps, bool)
        or not isinstance(fps, int | float)
        or not math.isfinite(fps)
        or fps <= 0
    ):
        raise InferenceError("FPS registrado deve ser positivo e finito.")
    if (
        not all(math.isfinite(value) for value in (interval.start_s, interval.end_s))
        or not 0 <= interval.start_s <= interval.end_s
        or round(interval.start_s * fps) != interval.start_frame
        or round(interval.end_s * fps) != interval.end_frame
    ):
        raise InferenceError("Intervalo útil inconsistente entre segundos, quadros e FPS.")
    # US-03 admite fim igual à duração (quadro exclusivo frame_count). Além
    # disso, round() no cadastro não pode incluir um timestamp antes da soltura
    # ou depois do fim: seleciona somente timestamps dentro dos limites reais.
    first_frame = max(interval.start_frame, math.ceil(interval.start_s * fps))
    last_frame = min(interval.end_frame, math.floor(interval.end_s * fps), frame_count - 1)
    # Ajusta produtos de ponto flutuante usando o mesmo timestamp do CSV.
    if first_frame > 0 and (first_frame - 1) / fps >= interval.start_s:
        first_frame -= 1
    if last_frame + 1 < frame_count and (last_frame + 1) / fps <= interval.end_s:
        last_frame += 1
    if first_frame > last_frame:
        raise InferenceError("O intervalo útil não contém nenhum quadro completo.")
    if not video.is_file():
        raise InferenceError(f"Vídeo local não encontrado: {video}")
    run_dir, record = _new_record(Path(output_root), model, "inferencia", device, batch_size)
    record.update(
        trial_id=trial_id,
        video=str(video),
        content_hash=expected_content_hash,
        interval=asdict(interval),
        processed_interval_frames={"start": first_frame, "end": last_frame},
        fps=fps,
        coordinate_frame="image",
        processed_frames=0,
        time_reference="seconds_from_video_start",
        missing_points=0,
        video_metadata={"width": width, "height": height, "frame_count": frame_count},
        backend_injected=backend_factory is not None,
        model_manifest_sha256=file_sha256(model_dir / "manifest.json"),
    )
    started = time.perf_counter()
    try:
        write_json(run_dir / "execucao.json", record)
        if file_sha256(video) != expected_content_hash:
            raise InferenceError("O hash do vídeo não corresponde ao trial cadastrado.")
        with offline_network():
            backend = (backend_factory or SleapBackend)(
                model_dir, device=device, batch_size=batch_size
            )
            with (run_dir / "pose.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(
                    [
                        "trial",
                        "quadro",
                        "time_s",
                        *[
                            column
                            for name in KEYPOINTS
                            for column in (
                                f"{name}_x_image",
                                f"{name}_y_image",
                                f"{name}_confidence",
                            )
                        ],
                    ]
                )

                def flush(indices: list[int], images: list[np.ndarray]) -> None:
                    points, scores = _predict(backend, images)
                    for index, coordinates, confidence in zip(indices, points, scores, strict=True):
                        values = []
                        for (x, y), score in zip(coordinates, confidence, strict=True):
                            if not (math.isfinite(x) and math.isfinite(y)):
                                record["missing_points"] += 1
                            values.extend(
                                "" if not math.isfinite(v) else float(v) for v in (x, y, score)
                            )
                        writer.writerow(
                            [trial_key(expected_content_hash), index, index / fps, *values]
                        )
                        record["processed_frames"] += 1

                indices, images = [], []
                for index, image in _sequential_frames(video, first_frame, last_frame):
                    if image.shape[:2] != (height, width):
                        raise InferenceError("Resolução do vídeo difere da cadastrada no trial.")
                    indices.append(index)
                    images.append(image)
                    if len(images) == batch_size:
                        flush(indices, images)
                        indices, images = [], []
                if images:
                    flush(indices, images)
        if file_sha256(video) != expected_content_hash:
            raise InferenceError("Vídeo foi alterado durante a inferência.")
        if _load_model(model_dir) != model:
            raise InferenceError("Modelo foi alterado durante a inferência.")
        record["status"] = "completed"
    except BaseException as exc:
        record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        if isinstance(exc, Exception):
            raise InferenceError(str(exc), run_dir=run_dir) from exc
        raise
    finally:
        _finish(run_dir, record, started)
    return run_dir


def predict_test_set(
    model_dir: str | Path,
    dataset_dir: str | Path,
    output_root: str | Path,
    *,
    device: str = "cpu",
    batch_size: int = 4,
    backend_factory: Callable | None = None,
) -> tuple[list[AnnotatedFrame], Path]:
    """Prediz os PNGs de teste congelados, sem fornecer rótulos ao backend."""
    _options(device, batch_size)
    model_dir, dataset_dir = Path(model_dir).resolve(), Path(dataset_dir).resolve()
    model, dataset = _load_model(model_dir), _load_dataset(dataset_dir)
    if (model["dataset_id"], model["maze_config_id"]) != (
        dataset["dataset_id"],
        dataset["maze_config_id"],
    ):
        raise InferenceError("Avaliação deve usar o conjunto congelado do treino e sua montagem.")
    selected = [f for f in dataset["frames"] if f["subset"] == "teste"]
    if not selected:
        raise InferenceError("Conjunto sem quadros de teste.")
    run_dir, record = _new_record(Path(output_root), model, "teste", device, batch_size)
    record.update(
        processed_frames=0,
        missing_points=0,
        backend_injected=backend_factory is not None,
        model_manifest_sha256=file_sha256(model_dir / "manifest.json"),
        dataset_manifest_sha256=file_sha256(dataset_dir / "manifest.json"),
        expected_frames=len(selected),
    )
    started, predictions = time.perf_counter(), []
    try:
        write_json(run_dir / "execucao.json", record)
        with offline_network():
            backend = (backend_factory or SleapBackend)(
                model_dir, device=device, batch_size=batch_size
            )
            # Um lote nunca mistura resoluções diferentes.
            pending, images = [], []

            def flush() -> None:
                points, _ = _predict(backend, images)
                for frame, coordinates in zip(pending, points, strict=True):
                    predictions.append(
                        AnnotatedFrame(
                            frame["trial"],
                            frame["frame_index"],
                            tuple(tuple(p) for p in coordinates),
                        )
                    )
                    record["processed_frames"] += 1
                    record["missing_points"] += sum(
                        not all(math.isfinite(value) for value in point) for point in coordinates
                    )

            for frame in selected:
                path = contained_path(dataset_dir, frame["image_path"])
                image = cv2.imread(str(path))
                if image is None:
                    raise InferenceError(f"PNG ilegível: {path}")
                if image.shape[:2] != (frame["height"], frame["width"]):
                    raise InferenceError(f"Resolução do PNG difere do manifesto: {path}")
                image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                if images and (len(images) == batch_size or images[0].shape != image.shape):
                    flush()
                    pending, images = [], []
                pending.append(frame)
                images.append(image)
            if images:
                flush()
        # Precisão integral: não arredondar próximo ao limiar estrito de meio corpo.
        with (run_dir / "predicoes.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                ["trial", "quadro", *[f"{p}_{axis}" for p in KEYPOINTS for axis in ("x", "y")]]
            )
            for frame in predictions:
                writer.writerow(
                    [
                        frame.trial,
                        frame.frame_index,
                        *[
                            value if math.isfinite(value) else ""
                            for point in frame.points
                            for value in point
                        ],
                    ]
                )
        if _load_dataset(dataset_dir) != dataset:
            raise InferenceError("Conjunto foi alterado durante a predição de teste.")
        if _load_model(model_dir) != model:
            raise InferenceError("Modelo foi alterado durante a predição de teste.")
        record.update(status="completed", processed_frames=len(predictions))
    except BaseException as exc:
        record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        if isinstance(exc, Exception):
            raise InferenceError(str(exc), run_dir=run_dir) from exc
        raise
    finally:
        _finish(run_dir, record, started)
    return predictions, run_dir
