"""Ciclo de registro US-07; execução pesada substituída por runner controlado."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from barnes.pose.dataset import prepare_dataset
from barnes.pose.training import (
    DEFAULT_CONFIG,
    DEFAULT_PARAMETERS,
    TrainingError,
    _validate_cuda_runtime,
    _worker,
    build_training_config,
    load_model_manifest,
    read_training_parameters,
    train_model,
)


@pytest.fixture
def prepared(dataset_inputs, fake_exporter):
    return prepare_dataset(**dataset_inputs, exporter=fake_exporter)


def successful_runner(config_path, log_path, environment):
    config = yaml.safe_load(config_path.read_text())
    assert config["data_config"]["test_file_path"] is None
    assert config["data_config"]["val_labels_path"] != config["data_config"]["train_labels_path"]
    assert config["trainer_config"]["trainer_accelerator"] == "gpu"
    assert config["trainer_config"]["use_wandb"] is False
    assert environment["WANDB_MODE"] == "disabled"
    assert environment["HF_HUB_OFFLINE"] == "1"
    output = Path(config["trainer_config"]["ckpt_dir"]) / config["trainer_config"]["run_name"]
    output.mkdir()
    (output / "best.ckpt").write_bytes(b"synthetic checkpoint for contract test")
    (output / "training_config.yaml").write_text(yaml.safe_dump(config))
    log_path.write_text("synthetic runner\n")


def test_run_records_provenance_and_never_passes_test_set(prepared, tmp_path):
    path = train_model(
        prepared,
        tmp_path / "models",
        DEFAULT_CONFIG,
        {"eligible": True, "hostname": "synthetic-gpu"},
        runner=successful_runner,
    )
    manifest = load_model_manifest(path)
    assert manifest["status"] == "completed"
    assert manifest["maze_config_id"] == 7
    assert manifest["elapsed_seconds"] >= 0
    assert manifest["parameters"]["seed"] == 42
    assert manifest["environment"]["packages"]
    assert manifest["source"]["snapshot"] == "source"
    assert (path / "source/barnes/pose/training.py").is_file()
    assert manifest["artifacts"]["sleap/best.ckpt"]
    assert manifest["data_uploaded"] is False
    second = train_model(
        prepared, tmp_path / "models", DEFAULT_CONFIG, {"eligible": True}, runner=successful_runner
    )
    assert second != path


def test_failed_run_is_not_a_model(prepared, tmp_path):
    def fail(*args):
        raise RuntimeError("out of GPU memory")

    with pytest.raises(TrainingError, match="memory") as error:
        train_model(prepared, tmp_path / "models", DEFAULT_CONFIG, {"eligible": True}, runner=fail)
    manifest_path = next((tmp_path / "models").glob("*/manifest.json"))
    manifest = json.loads(manifest_path.read_text())
    assert manifest["status"] == "failed"
    assert manifest["finished_at"]
    assert "out of GPU memory" in manifest["error"]
    assert error.value.model_dir == manifest_path.parent
    with pytest.raises(TrainingError, match="concluído"):
        load_model_manifest(manifest_path.parent)


def test_checks_hardware_before_runner(prepared, tmp_path):
    def must_not_run(*args):
        pytest.fail("Ineligible machine must not start a trainer")

    with pytest.raises(TrainingError, match="Máquina"):
        train_model(
            prepared, tmp_path / "models", DEFAULT_CONFIG, {"eligible": False}, runner=must_not_run
        )


def test_success_without_checkpoint_is_failure(prepared, tmp_path):
    with pytest.raises(TrainingError, match="checkpoint"):
        train_model(
            prepared,
            tmp_path / "models",
            DEFAULT_CONFIG,
            {"eligible": True},
            runner=lambda *args: None,
        )


def test_refuses_modified_checkpoint(prepared, tmp_path):
    path = train_model(
        prepared, tmp_path / "models", DEFAULT_CONFIG, {"eligible": True}, runner=successful_runner
    )
    (path / "sleap/best.ckpt").write_bytes(b"corrupt")
    with pytest.raises(TrainingError, match="alterado"):
        load_model_manifest(path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_epochs", 0),
        ("scale", 0),
        ("scale", 2),
        ("learning_rate", float("nan")),
        ("seed", 2**32),
        ("max_stride", 15),
        ("output_stride", 32),
        ("batch_size", True),
        ("download_url", "https://example.invalid/model"),
    ],
)
def test_rejects_invalid_parameters(tmp_path, field, value):
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump({"sleap_nn_version": "0.3.1", "parameters": {field: value}}))
    with pytest.raises(TrainingError):
        read_training_parameters(path)


def test_native_config_matches_installed_sleap_schema(tmp_path):
    """Contrato executável ao instalar o extra pose; não inicia treino/download."""
    pytest.importorskip("sleap_nn")
    from omegaconf import OmegaConf
    from sleap_nn.config.training_job_config import verify_training_cfg

    config = build_training_config(tmp_path / "dataset", tmp_path / "model", DEFAULT_PARAMETERS)
    resolved = verify_training_cfg(OmegaConf.create(config))
    assert resolved.model_config.head_configs.single_instance.confmaps.part_names == [
        "focinho",
        "centro_corpo",
        "base_cauda",
    ]
    assert resolved.trainer_config.use_wandb is False
    assert resolved.data_config.test_file_path is None


@pytest.fixture
def fake_torch():
    class Tensor:
        def __mul__(self, value):
            self.value = value
            return self

        def item(self):
            return self.value

    return SimpleNamespace(
        version=SimpleNamespace(cuda="12.8"),
        cuda=SimpleNamespace(
            is_available=lambda: True,
            device_count=lambda: 2,
            get_device_properties=lambda index: SimpleNamespace(
                total_memory=(2 if index == 0 else 8) * 1024**3, name=f"NVIDIA test {index}"
            ),
            get_device_capability=lambda index: (8, 6),
            synchronize=lambda index: None,
        ),
        ones=lambda *args, **kwargs: Tensor(),
    )


def test_runtime_requires_the_selected_gpu_to_meet_minimum(fake_torch):
    hardware = {"eligible": True, "ram_bytes": 16_000_000_000}
    with pytest.raises(TrainingError, match="selecionada"):
        _validate_cuda_runtime(fake_torch, hardware, 0)
    result = _validate_cuda_runtime(fake_torch, hardware, 1)
    assert result["allocation_and_kernel_check"] == "passed"
    assert result["gpu_index"] == 1
    with pytest.raises(TrainingError, match="não existe"):
        _validate_cuda_runtime(fake_torch, hardware, 2)


def test_runtime_rejects_ram_and_driver_incompatibility(fake_torch):
    with pytest.raises(TrainingError, match="RAM"):
        _validate_cuda_runtime(fake_torch, {"eligible": True, "ram_bytes": 8_000_000_000}, 1)

    def bad_driver(*args, **kwargs):
        raise RuntimeError("driver mismatch")

    fake_torch.ones = bad_driver
    with pytest.raises(TrainingError, match="Driver/CUDA"):
        _validate_cuda_runtime(fake_torch, {"eligible": True, "ram_bytes": 16_000_000_000}, 1)


def test_worker_rechecks_machine_with_offline_guard(monkeypatch, tmp_path):
    import socket

    from barnes.pose.offline import OfflineNetworkError

    def inspect():
        with pytest.raises(OfflineNetworkError):
            socket.getaddrinfo("example.invalid", 443)
        return {"eligible": False, "ram_bytes": 8_000_000_000}

    monkeypatch.setattr("barnes.pose.training.inspect_hardware", inspect)
    with pytest.raises(TrainingError, match="Hardware"):
        _worker(tmp_path / "config.yaml")
    runtime = json.loads((tmp_path / "runtime.json").read_text())
    assert runtime["status"] == "failed"
    assert runtime["hardware"]["eligible"] is False
