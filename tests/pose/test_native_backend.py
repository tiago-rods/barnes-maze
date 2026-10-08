"""Contrato real opcional SLEAP: dados sintéticos, sem atestar US-07/US-08.

Executar em um ambiente CPU separado também é permitido: este teste chama a
API nativa diretamente e não reduz a exigência NVIDIA do comando de treino.
"""

from pathlib import Path

import numpy as np
import pytest

from barnes.pose.dataset import prepare_dataset
from barnes.pose.offline import offline_network
from barnes.pose.training import DEFAULT_PARAMETERS, build_training_config


def test_native_backend_synthetic_roundtrip(dataset_inputs, tmp_path):
    pytest.importorskip("sleap_nn")
    with offline_network():
        import torch
        from omegaconf import OmegaConf
        from sleap_nn.config.training_job_config import verify_training_cfg
        from sleap_nn.train import run_training

        from barnes.pose.inference import SleapBackend

        dataset = prepare_dataset(**dataset_inputs)
        model = tmp_path / "synthetic-model"
        parameters = DEFAULT_PARAMETERS | {
            "max_epochs": 1,
            "batch_size": 1,
            "scale": 1.0,
            "filters": 4,
            "max_stride": 4,
            "output_stride": 1,
            "early_stopping_patience": 1,
        }
        config = build_training_config(dataset, model, parameters)
        config["data_config"]["use_augmentations_train"] = False
        config["trainer_config"].update(
            trainer_accelerator="cpu",
            trainer_device_indices=None,
            trainer_devices=1,
            min_train_steps_per_epoch=1,
            train_steps_per_epoch=1,
        )
        resolved = verify_training_cfg(OmegaConf.create(config))
        previous_threads = torch.get_num_threads()
        torch.set_num_threads(1)
        try:
            run_training(resolved)
            assert (model / "sleap/best.ckpt").stat().st_size > 0
            assert (model / "sleap/training_config.yaml").is_file()
            backend = SleapBackend(Path(model), device="cpu", batch_size=2)
            points, confidence = backend.predict(np.full((2, 32, 40, 3), 80, dtype=np.uint8))
            assert points.shape == (2, 3, 2)
            assert confidence.shape == (2, 3)
            # Shapes test the contract; one epoch on uniform images proves no quality.
            assert np.issubdtype(points.dtype, np.floating)
        finally:
            torch.set_num_threads(previous_threads)
