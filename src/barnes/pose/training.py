"""Treino SLEAP-NN/PyTorch local com registro e pesos verificáveis (US-07)."""

from __future__ import annotations

import importlib.metadata
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import yaml

from barnes.pose.annotations import KEYPOINTS
from barnes.pose.dataset import contained_path, file_sha256, load_dataset_manifest, write_json
from barnes.pose.environment import MIN_RAM_BYTES, inspect_hardware
from barnes.pose.offline import offline_network
from barnes.provenance import git_state

SLEAP_NN_VERSION = "0.3.1"
SLEAP_IO_VERSION = "0.9.2"
TORCH_VERSION = "2.7.1"
TORCHVISION_VERSION = "0.22.1"
DEFAULT_CONFIG = Path("configs/pose/single_animal.yaml")
DEFAULT_PARAMETERS = {
    "seed": 42,
    "max_epochs": 100,
    "batch_size": 2,
    "learning_rate": 0.0001,
    "scale": 0.5,
    "filters": 16,
    "max_stride": 16,
    "output_stride": 2,
    "sigma": 2.5,
    "rotation_degrees": 15.0,
    "early_stopping_patience": 10,
    "gpu_index": 0,
}


class TrainingError(ValueError):
    """Treino não pode ser iniciado ou seus artefatos não são válidos."""

    def __init__(self, message: str, *, model_dir: Path | None = None) -> None:
        super().__init__(message)
        self.model_dir = model_dir


def read_training_parameters(path: str | Path) -> dict:
    """Lê parâmetros explícitos, sem permitir URLs, plugins ou pesos externos."""
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict) or document.get("sleap_nn_version") != SLEAP_NN_VERSION:
        raise TrainingError(f"A configuração deve fixar sleap_nn_version: {SLEAP_NN_VERSION}.")
    if set(document) - {"sleap_nn_version", "parameters"}:
        raise TrainingError("Campos de configuração desconhecidos.")
    values = document.get("parameters", {})
    if not isinstance(values, dict) or set(values) - set(DEFAULT_PARAMETERS):
        raise TrainingError("Hiperparâmetros desconhecidos; use configs/pose/single_animal.yaml.")
    values = DEFAULT_PARAMETERS | values
    for name, default in DEFAULT_PARAMETERS.items():
        value = values[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise TrainingError(f"{name} deve ser um número finito.")
        if isinstance(default, int) and not isinstance(value, int):
            raise TrainingError(f"{name} deve ser inteiro.")
        minimum = 0 if name in {"seed", "gpu_index", "rotation_degrees"} else 1e-12
        if value < minimum:
            raise TrainingError(f"Valor inválido de {name}: {value}.")
    if values["scale"] > 1 or values["rotation_degrees"] > 180:
        raise TrainingError("scale deve estar em (0,1]; rotation_degrees em [0,180].")
    if any(values[key] & (values[key] - 1) for key in ("max_stride", "output_stride")):
        raise TrainingError("max_stride e output_stride devem ser potências de dois.")
    if values["output_stride"] > values["max_stride"]:
        raise TrainingError("output_stride não pode exceder max_stride.")
    if values["seed"] >= 2**32:
        raise TrainingError("seed deve ser menor que 2**32.")
    return values


def build_training_config(dataset_dir: Path, model_dir: Path, parameters: dict) -> dict:
    """Constrói configuração nativa; o conjunto de teste nunca entra no treino."""
    p = parameters
    return {
        "sleap_nn_version": SLEAP_NN_VERSION,
        "data_config": {
            "train_labels_path": [str(dataset_dir / "treino.pkg.slp")],
            "val_labels_path": [str(dataset_dir / "validacao.pkg.slp")],
            "test_file_path": None,
            "use_same_data_for_val": False,
            "user_instances_only": True,
            "data_pipeline_fw": "torch_dataset",
            "use_augmentations_train": True,
            "preprocessing": {"ensure_grayscale": True, "ensure_rgb": False, "scale": p["scale"]},
            "augmentation_config": {
                "geometric": {
                    "rotation_min": -p["rotation_degrees"],
                    "rotation_max": p["rotation_degrees"],
                    "scale_min": 1.0,
                    "scale_max": 1.0,
                    "translate_width": 0.0,
                    "translate_height": 0.0,
                    "affine_p": 1.0,
                }
            },
        },
        "model_config": {
            "backbone_config": {
                "unet": {
                    "in_channels": 1,
                    "filters": p["filters"],
                    "max_stride": p["max_stride"],
                    "output_stride": p["output_stride"],
                }
            },
            "head_configs": {
                "single_instance": {
                    "confmaps": {
                        "part_names": list(KEYPOINTS),
                        "sigma": p["sigma"],
                        "output_stride": p["output_stride"],
                    }
                }
            },
            "pretrained_backbone_weights": None,
            "pretrained_head_weights": None,
        },
        "trainer_config": {
            "seed": p["seed"],
            "max_epochs": p["max_epochs"],
            "train_data_loader": {"batch_size": p["batch_size"], "shuffle": True, "num_workers": 0},
            "val_data_loader": {"batch_size": p["batch_size"], "shuffle": False, "num_workers": 0},
            "trainer_accelerator": "gpu",
            "trainer_devices": 1,
            "trainer_device_indices": [p["gpu_index"]],
            "trainer_strategy": "auto",
            "min_train_steps_per_epoch": 1,
            "optimizer_name": "Adam",
            "optimizer": {"lr": p["learning_rate"]},
            "early_stopping": {
                "stop_training_on_plateau": True,
                "patience": p["early_stopping_patience"],
                "min_delta": 1e-8,
            },
            "save_ckpt": True,
            "ckpt_dir": str(model_dir),
            "run_name": "sleap",
            "model_ckpt": {
                "save_top_k": 1,
                "save_last": True,
                "monitor": "val/loss",
                "mode": "min",
            },
            "use_wandb": False,
            "visualize_preds_during_training": False,
            "enable_progress_bar": False,
            "resume_ckpt_path": None,
            "zmq": {"controller_port": None, "publish_port": None},
        },
    }


def environment_record() -> dict:
    """Registra versões instaladas e plataforma, sem expor variáveis de ambiente."""
    packages = {
        package.metadata["Name"]: package.version
        for package in importlib.metadata.distributions()
        if package.metadata["Name"]
    }
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "machine_architecture": platform.machine(),
        "hostname": platform.node(),
        "packages": dict(sorted(packages.items(), key=lambda item: item[0].lower())),
    }


def _source_record(model_dir: Path) -> dict:
    """Preserva o código Python executável e a revisão, inclusive mudanças não commitadas."""
    src = Path(__file__).resolve().parents[1]
    for path in src.rglob("*.py"):
        target = model_dir / "source" / "barnes" / path.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    repo = src.parents[1]
    for name in ("pyproject.toml", "uv.lock"):
        if (repo / name).is_file():
            shutil.copyfile(repo / name, model_dir / "source" / name)
    state = git_state(repo)
    return {"git_commit": state.commit, "git_dirty": state.dirty, "snapshot": "source"}


def _run_worker(config_path: Path, log_path: Path, environment: dict[str, str]) -> None:
    with log_path.open("w", encoding="utf-8") as log:
        subprocess.run(
            [sys.executable, "-m", "barnes.pose.training", "--worker", str(config_path)],
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )


def train_model(
    dataset_dir: str | Path,
    models_dir: str | Path,
    config_path: str | Path,
    machine_report: dict,
    *,
    runner: Callable[[Path, Path, dict[str, str]], None] | None = None,
) -> Path:
    """Executa treino local e preserva o manifesto mesmo em falha/interrupção.

    ``machine_report`` é o levantamento real do hardware usado pelo CLI.
    O worker ainda verifica CUDA e a memória da GPU selecionada no PyTorch.
    ``runner`` permite testar o ciclo de artefatos sem GPU, sem alegar treino real.
    """
    dataset_dir = Path(dataset_dir).resolve()
    dataset = load_dataset_manifest(dataset_dir)
    parameters = read_training_parameters(config_path)
    model_id = f"sleap-maze-{dataset['maze_config_id']}-{uuid.uuid4().hex}"
    model_dir = Path(models_dir).resolve() / model_id
    model_dir.mkdir(parents=True, exist_ok=False)
    native_config = build_training_config(dataset_dir, model_dir, parameters)
    (model_dir / "config.yaml").write_text(
        yaml.safe_dump(native_config, sort_keys=False), encoding="utf-8"
    )
    (model_dir / "parameters.yaml").write_text(
        yaml.safe_dump({"sleap_nn_version": SLEAP_NN_VERSION, "parameters": parameters}),
        encoding="utf-8",
    )
    shutil.copyfile(dataset_dir / "manifest.json", model_dir / "dataset_manifest.json")
    manifest = {
        "schema_version": 1,
        "model_id": model_id,
        "status": "running",
        "maze_config_id": dataset["maze_config_id"],
        "dataset_id": dataset["dataset_id"],
        "dataset_path": str(dataset_dir),
        "keypoints": list(KEYPOINTS),
        "started_at": datetime.now(UTC).isoformat(),
        "parameters": parameters,
        "machine": machine_report,
        "environment": environment_record(),
        "backend": "sleap-nn",
        "sleap_nn_version": SLEAP_NN_VERSION,
        "config_path": "config.yaml",
        "checkpoint": "sleap/best.ckpt",
        "deterministic_algorithms": True,
        "data_uploaded": False,
        "artifacts": {},
    }
    write_json(model_dir / "manifest.json", manifest)
    started = time.perf_counter()
    try:
        if machine_report.get("eligible") is not True:
            raise TrainingError("Máquina não atende NVIDIA >=4 GiB VRAM e RAM >=16 GB.")
        manifest["source"] = _source_record(model_dir)
        write_json(model_dir / "manifest.json", manifest)
        environment = os.environ.copy()
        environment.update(
            WANDB_MODE="disabled",
            HF_HUB_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
            HF_HUB_DISABLE_TELEMETRY="1",
            DO_NOT_TRACK="1",
            PYTHONHASHSEED=str(parameters["seed"]),
            CUBLAS_WORKSPACE_CONFIG=":4096:8",
            PYTHONUTF8="1",
        )
        (runner or _run_worker)(model_dir / "config.yaml", model_dir / "training.log", environment)
        required = ("sleap/best.ckpt", "sleap/training_config.yaml")
        if any(
            not (model_dir / name).is_file() or not (model_dir / name).stat().st_size
            for name in required
        ):
            raise TrainingError("SLEAP terminou sem checkpoint/configuração; treino não concluído.")
        # Verifica novamente para registrar alterações concorrentes nos dados como falha.
        load_dataset_manifest(dataset_dir)
        manifest["artifacts"] = {
            path.relative_to(model_dir).as_posix(): file_sha256(path)
            for path in sorted(model_dir.rglob("*"))
            if path.is_file() and path.name != "manifest.json"
        }
        manifest["status"] = "completed"
    except BaseException as exc:
        detail = f"{type(exc).__name__}: {exc}"
        runtime_path = model_dir / "runtime.json"
        if runtime_path.is_file():
            try:
                runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
                if runtime.get("error"):
                    detail += f"; worker: {runtime['error']}"
            except (OSError, ValueError):
                pass
        manifest.update(status="failed", error=detail)
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise TrainingError(
            f"Treino falhou: {detail}. Registro preservado em {model_dir}.", model_dir=model_dir
        ) from exc
    finally:
        runtime_path = model_dir / "runtime.json"
        if runtime_path.is_file():
            try:
                manifest["runtime"] = json.loads(runtime_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        manifest["finished_at"] = datetime.now(UTC).isoformat()
        manifest["elapsed_seconds"] = time.perf_counter() - started
        write_json(model_dir / "manifest.json", manifest)
    return model_dir


def load_model_manifest(model_dir: str | Path, verify: bool = True) -> dict:
    """Aceita somente modelos concluídos, com pesos e configuração íntegros."""
    root = Path(model_dir).resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "completed" or manifest.get("schema_version") != 1:
        raise TrainingError("Modelo sem treino concluído ou manifesto incompatível.")
    if manifest.get("keypoints") != list(KEYPOINTS):
        raise TrainingError("Esqueleto do modelo incompatível com os três pontos de Barnes.")
    required = {
        manifest["checkpoint"],
        manifest["config_path"],
        "dataset_manifest.json",
        "sleap/training_config.yaml",
    }
    if not required.issubset(manifest.get("artifacts", {})):
        raise TrainingError("Manifesto sem hashes dos pesos/configurações obrigatórios.")
    if verify:
        for relative, expected in manifest["artifacts"].items():
            path = contained_path(root, relative)
            if not path.is_file() or file_sha256(path) != expected:
                raise TrainingError(f"Artefato do modelo ausente ou alterado: {relative}")
        dataset = json.loads((root / "dataset_manifest.json").read_text(encoding="utf-8"))
        for key in ("dataset_id", "maze_config_id", "keypoints"):
            if manifest.get(key) != dataset.get(key):
                raise TrainingError(f"Modelo e conjunto de origem divergem em {key}.")
    return manifest


def _validate_cuda_runtime(torch, hardware: dict, gpu_index: int) -> dict:
    """Verifica a GPU realmente escolhida e executa um kernel antes do treino."""
    if isinstance(gpu_index, bool) or not isinstance(gpu_index, int) or gpu_index < 0:
        raise TrainingError("Índice da GPU deve ser um inteiro não negativo.")
    if hardware.get("eligible") is not True or (hardware.get("ram_bytes") or 0) < MIN_RAM_BYTES:
        raise TrainingError("Hardware atual não atende NVIDIA >=4 GiB e RAM >=16 GB.")
    if not torch.cuda.is_available() or torch.version.cuda is None:
        raise TrainingError("PyTorch não detecta CUDA/NVIDIA; instale o build CUDA definido.")
    if torch.version.cuda != "12.8":
        raise TrainingError("Este perfil exige o build PyTorch CUDA 12.8 (cu128).")
    if gpu_index >= torch.cuda.device_count():
        raise TrainingError(f"GPU CUDA {gpu_index} não existe entre os dispositivos visíveis.")
    properties = torch.cuda.get_device_properties(gpu_index)
    if properties.total_memory < 4 * 1024**3:
        raise TrainingError("A GPU selecionada tem menos de 4 GiB de VRAM.")
    try:
        probe = torch.ones(1, device=f"cuda:{gpu_index}") * 2
        torch.cuda.synchronize(gpu_index)
        if float(probe.item()) != 2.0:
            raise TrainingError("O teste de cálculo CUDA produziu resultado inválido.")
        del probe
    except RuntimeError as exc:
        raise TrainingError(f"Driver/CUDA não executa um kernel na GPU selecionada: {exc}") from exc
    return {
        "cuda_version": torch.version.cuda,
        "gpu_index": gpu_index,
        "gpu_name": properties.name,
        "gpu_memory_bytes": properties.total_memory,
        "compute_capability": list(torch.cuda.get_device_capability(gpu_index)),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "allocation_and_kernel_check": "passed",
    }


def _worker(config_path: Path) -> None:
    """Processo dedicado, com hardware real e guarda offline também nos imports."""
    runtime: dict = {"status": "checking", "offline_guard": True}
    try:
        with offline_network():
            runtime["hardware"] = inspect_hardware()
            write_json(config_path.parent / "runtime.json", runtime)
            if runtime["hardware"].get("eligible") is not True:
                raise TrainingError("Hardware atual não atende NVIDIA >=4 GiB e RAM >=16 GB.")
            expected = (
                ("sleap-nn", SLEAP_NN_VERSION),
                ("sleap-io", SLEAP_IO_VERSION),
                ("torch", TORCH_VERSION),
                ("torchvision", TORCHVISION_VERSION),
            )
            runtime["packages"] = {}
            for package, version in expected:
                actual = importlib.metadata.version(package)
                runtime["packages"][package] = actual
                if actual.partition("+")[0] != version:
                    raise TrainingError(f"Treino exige {package}=={version}; encontrado {actual}.")
            import torch
            from omegaconf import OmegaConf
            from sleap_nn.config.training_job_config import verify_training_cfg
            from sleap_nn.train import run_training

            config = verify_training_cfg(OmegaConf.load(config_path))
            index = config.trainer_config.trainer_device_indices[0]
            runtime["cuda"] = _validate_cuda_runtime(torch, runtime["hardware"], index)
            runtime["status"] = "ready"
            write_json(config_path.parent / "runtime.json", runtime)
            torch.backends.cudnn.benchmark = False
            torch.backends.cudnn.deterministic = True
            torch.use_deterministic_algorithms(True)
            OmegaConf.save(config, config_path.parent / "resolved_config.yaml")
            run_training(config)
    except BaseException as exc:
        runtime.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        write_json(config_path.parent / "runtime.json", runtime)
        raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Worker interno de treino Barnes/SLEAP-NN.")
    parser.add_argument("--worker", required=True, type=Path)
    _worker(parser.parse_args().worker)
