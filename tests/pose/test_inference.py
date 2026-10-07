"""Contratos de inferência com pixels sintéticos e backend falso; não validam SLEAP/GPU."""

import csv
import json
import math
import os
import shutil
import socket
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import ClassVar
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from barnes.io.trim import TrialInterval, interval_from_seconds
from barnes.pose import inference
from barnes.pose.annotations import KEYPOINTS, AnnotatedFrame, frame_filename, write_annotations_csv
from barnes.pose.dataset import file_sha256, prepare_dataset, write_json
from barnes.pose.inference import (
    InferenceError,
    SleapBackend,
    infer_trial,
    load_inference_record,
    predict_test_set,
)
from barnes.pose.offline import OfflineNetworkError
from barnes.pose.split import ManifestRow, write_manifest


@pytest.fixture
def package_and_model(tmp_path, monkeypatch):
    """Artefatos falsos marcados como tal, mas com hashes/pacote reais para testar integridade."""
    monkeypatch.setattr(inference, "environment_record", lambda: {"unit_test_only": True})
    source = tmp_path / "annotation-source"
    frames, split = [], []
    for trial, subset, indices, color in (
        ("111111111111", "treino", [0], 10),
        ("222222222222", "validacao", [0], 20),
        ("333333333333", "teste", [5, 9, 13], 30),
    ):
        folder = source / trial / "quadros"
        folder.mkdir(parents=True)
        (folder.parent / "amostragem.csv").write_text("maze_config_id\n7\n", encoding="utf-8")
        for index in indices:
            # Testa também o agrupamento de imagens com resoluções diferentes.
            width = 64 if index == 13 else 48
            image = np.zeros((32, width, 3), dtype=np.uint8)
            image[:] = (color, 50, color + index)
            assert cv2.imwrite(str(folder / frame_filename(index)), image)
            frames.append(AnnotatedFrame(trial, index, ((18.0, 10.0), (10.0, 10.0), (2.0, 10.0))))
            split.append(ManifestRow(trial, index, subset))
    write_annotations_csv(frames, source / "anotacoes.csv")
    write_manifest(split, source / "divisao.csv")

    def fake_exporter(selected, root, output):
        output.write_bytes(b"UNIT TEST ONLY: not a real SLP or training dataset")

    dataset = prepare_dataset(
        source / "anotacoes.csv",
        source / "divisao.csv",
        source,
        tmp_path / "packages",
        7,
        exporter=fake_exporter,
    )
    dataset_manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    model = tmp_path / "unit-only-model"
    (model / "sleap").mkdir(parents=True)
    for relative in ("sleap/best.ckpt", "sleap/training_config.yaml", "config.yaml"):
        (model / relative).write_text("UNIT TEST ONLY: fake backend artifact", encoding="utf-8")
    shutil.copyfile(dataset / "manifest.json", model / "dataset_manifest.json")
    write_json(
        model / "manifest.json",
        {
            "schema_version": 1,
            "status": "completed",
            "model_id": "unit-only-model",
            "maze_config_id": 7,
            "dataset_id": dataset_manifest["dataset_id"],
            "keypoints": list(KEYPOINTS),
            "checkpoint": "sleap/best.ckpt",
            "config_path": "config.yaml",
            "artifacts": {
                path.relative_to(model).as_posix(): file_sha256(path)
                for path in model.rglob("*")
                if path.is_file()
            },
        },
    )
    return SimpleNamespace(dataset=dataset, model=model, manifest=dataset_manifest, source=source)


@pytest.fixture
def pixel_backend():
    class PixelsOnlyBackend:
        """Fake explícito: coordenadas derivadas de pixels, sem conhecer ground truth."""

        images: ClassVar[list] = []
        initialized: ClassVar[list] = []

        def __init__(self, model_dir, *, device, batch_size):
            self.initialized.append((model_dir, device, batch_size))
            assert os.environ["HF_HUB_OFFLINE"] == "1"
            with pytest.raises(OfflineNetworkError):
                socket.gethostbyname("must-not-resolve.invalid")

        def predict(self, images):
            assert isinstance(images, np.ndarray)
            assert images.dtype == np.uint8 and images.ndim == 4 and images.shape[-1] == 3
            self.images.append(images.copy())
            points = np.zeros((len(images), 3, 2), dtype=float)
            points[:, :, 0] = images[:, 0, 0, 0, None]
            points[:, :, 1] = images[:, 0, 0, 1, None]
            return points, np.full((len(images), 3), 0.75)

    return PixelsOnlyBackend


@pytest.fixture
def video_inputs(tmp_path):
    video = tmp_path / "synthetic.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (48, 32))
    assert writer.isOpened()
    try:
        for index in range(8):
            image = np.full((32, 48, 3), (5, 70, index * 25), dtype=np.uint8)
            writer.write(image)
    finally:
        writer.release()
    return {
        "video": video,
        "trial_id": 12,
        "maze_config_id": 7,
        "interval": interval_from_seconds(0.2, 0.4, 10.0, manually_adjusted=True),
        "expected_content_hash": file_sha256(video),
        "fps": 10.0,
        "frame_count": 8,
        "width": 48,
        "height": 32,
    }


def _read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_trial_decodes_sequentially_and_only_predicts_registered_interval(
    package_and_model, video_inputs, pixel_backend, tmp_path, monkeypatch
):
    original_capture = cv2.VideoCapture
    reads = []

    class CaptureWithoutSeek:
        def __init__(self, path):
            self.capture = original_capture(path)

        def isOpened(self):
            return self.capture.isOpened()

        def read(self):
            reads.append(len(reads))
            return self.capture.read()

        def set(self, *args):
            pytest.fail("Inferência não deve fazer seek para recuperar índices de B-frames")

        def release(self):
            self.capture.release()

    monkeypatch.setattr(cv2, "VideoCapture", CaptureWithoutSeek)
    run = infer_trial(
        package_and_model.model,
        output_root=tmp_path / "runs",
        **video_inputs,
        batch_size=2,
        backend_factory=pixel_backend,
    )
    record = load_inference_record(run)
    rows = _read_csv(run / "pose.csv")
    assert reads == [0, 1, 2, 3, 4]
    assert [int(row["quadro"]) for row in rows] == [2, 3, 4]
    assert [float(row["time_s"]) for row in rows] == [0.2, 0.3, 0.4]
    assert [len(images) for images in pixel_backend.images] == [2, 1]
    assert all(row["trial"] == video_inputs["expected_content_hash"][:12] for row in rows)
    assert record["status"] == "completed"
    assert record["processed_frames"] == 3
    assert record["missing_points"] == 0
    assert record["coordinate_frame"] == "image"
    assert record["time_reference"] == "seconds_from_video_start"
    assert record["backend_injected"] is True
    assert record["network_policy"] == "python_loopback_only"
    assert record["physical_network_disconnection_verified"] is False
    assert record["duration_seconds"] >= 0
    assert record["source"]["python_files_sha256"]["pose/inference.py"] == file_sha256(
        Path(inference.__file__)
    )
    # Os três pixels do intervalo, após BGR -> RGB, controlam o backend falso.
    capture = original_capture(str(video_inputs["video"]))
    try:
        decoded = [capture.read()[1] for _ in range(5)]
    finally:
        capture.release()
    for row, image in zip(rows, decoded[2:], strict=True):
        assert float(row["focinho_x_image"]) == float(image[0, 0, 2])


@pytest.mark.parametrize("start,end,indices", [(0.0, 0.8, list(range(8))), (0.21, 0.39, [3])])
def test_trial_full_duration_and_fractional_boundaries(
    package_and_model, video_inputs, pixel_backend, tmp_path, start, end, indices
):
    video_inputs["interval"] = interval_from_seconds(start, end, 10.0, manually_adjusted=True)
    run = infer_trial(
        package_and_model.model,
        output_root=tmp_path / "runs",
        **video_inputs,
        backend_factory=pixel_backend,
    )
    rows = _read_csv(run / "pose.csv")
    assert [int(row["quadro"]) for row in rows] == indices
    assert all(start <= float(row["time_s"]) <= end for row in rows)
    assert load_inference_record(run)["processed_interval_frames"] == {
        "start": indices[0],
        "end": indices[-1],
    }


def test_test_predictions_receive_only_held_out_pixels_and_keep_precision(
    package_and_model, pixel_backend, tmp_path
):
    original_predict = pixel_backend.predict

    def fractional_predict(self, images):
        points, scores = original_predict(self, images)
        points += 0.123456789
        return points, scores

    pixel_backend.predict = fractional_predict
    predictions, run = predict_test_set(
        package_and_model.model,
        package_and_model.dataset,
        tmp_path / "runs",
        batch_size=2,
        backend_factory=pixel_backend,
    )
    assert [(frame.trial, frame.frame_index) for frame in predictions] == [
        ("333333333333", 5),
        ("333333333333", 9),
        ("333333333333", 13),
    ]
    assert [batch.shape for batch in pixel_backend.images] == [(2, 32, 48, 3), (1, 32, 64, 3)]
    assert [int(image[0, 0, 0]) for batch in pixel_backend.images for image in batch] == [
        35,
        39,
        43,
    ]
    rows = _read_csv(run / "predicoes.csv")
    assert float(rows[0]["focinho_x"]) == 35.123456789
    assert rows[0]["focinho_x"] != "18.0"  # Não copiou a anotação manual.
    record = load_inference_record(run)
    assert record["processed_frames"] == record["expected_frames"] == 3
    assert record["dataset_manifest_sha256"] == file_sha256(
        package_and_model.dataset / "manifest.json"
    )


def test_missing_and_nonfinite_predictions_remain_in_trial_output(
    package_and_model, video_inputs, pixel_backend, tmp_path
):
    original_predict = pixel_backend.predict

    def with_missing(self, images):
        points, scores = original_predict(self, images)
        points[0, 0] = [math.nan, math.inf]
        scores[0, 0] = math.inf
        points.setflags(write=False)
        scores.setflags(write=False)
        return points, scores

    pixel_backend.predict = with_missing
    run = infer_trial(
        package_and_model.model,
        output_root=tmp_path / "runs",
        **video_inputs,
        batch_size=10,
        backend_factory=pixel_backend,
    )
    rows = _read_csv(run / "pose.csv")
    assert len(rows) == 3
    assert rows[0]["focinho_x_image"] == rows[0]["focinho_y_image"] == ""
    assert rows[0]["focinho_confidence"] == ""
    assert load_inference_record(run)["missing_points"] == 1


@pytest.mark.parametrize(
    "parameter,value,match",
    [
        ("maze_config_id", 8, "Montagem"),
        ("fps", 0.0, "FPS"),
        ("width", 0, "width"),
        ("batch_size", 0, "batch_size"),
        ("device", "https://remote", "device"),
        ("interval", None, "intervalo"),
        ("interval", TrialInterval(0, 2, 0, 20, False), "intervalo"),
        ("interval", TrialInterval(0.2, 0.4, 1, 4, False), "inconsistente"),
    ],
)
def test_invalid_trial_inputs_do_not_start_backend(
    package_and_model, video_inputs, pixel_backend, tmp_path, parameter, value, match
):
    video_inputs[parameter] = value
    with pytest.raises(InferenceError, match=match) as caught:
        infer_trial(
            package_and_model.model,
            output_root=tmp_path / "runs",
            **video_inputs,
            backend_factory=pixel_backend,
        )
    assert caught.value.run_dir is None
    assert not pixel_backend.initialized
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("bad_input,match", [("hash", "hash"), ("resolution", "Resolução")])
def test_video_mismatch_records_failed_run_with_accessible_path(
    package_and_model, video_inputs, pixel_backend, tmp_path, bad_input, match
):
    if bad_input == "hash":
        video_inputs["expected_content_hash"] = "a" * 64
    else:
        video_inputs["width"] += 1
    with pytest.raises(InferenceError, match=match) as caught:
        infer_trial(
            package_and_model.model,
            output_root=tmp_path / "runs",
            **video_inputs,
            backend_factory=pixel_backend,
        )
    record = load_inference_record(caught.value.run_dir)
    assert record["status"] == "failed"
    assert record["trial_id"] == 12
    assert record["processed_frames"] == 0
    assert record["duration_seconds"] >= 0
    assert not pixel_backend.images


def test_early_video_end_records_failed_run(
    package_and_model, video_inputs, pixel_backend, tmp_path
):
    video_inputs.update(
        frame_count=100,
        interval=interval_from_seconds(0.2, 0.9, 10.0, manually_adjusted=False),
    )
    with pytest.raises(InferenceError, match="terminou/falhou") as caught:
        infer_trial(
            package_and_model.model,
            output_root=tmp_path / "runs",
            **video_inputs,
            batch_size=2,
            backend_factory=pixel_backend,
        )
    record = load_inference_record(caught.value.run_dir)
    assert record["status"] == "failed"
    assert record["processed_frames"] == 6


@pytest.mark.parametrize("stage", ["constructor", "prediction", "wrong_shape"])
def test_backend_failures_preserve_run_and_restore_network(
    package_and_model, pixel_backend, tmp_path, stage
):
    old_getaddrinfo = socket.getaddrinfo
    old_environment = dict(os.environ)
    if stage == "constructor":

        def fail(*args, **kwargs):
            raise RuntimeError("backend failed to load")

        factory = fail
    else:

        def fail(self, images):
            if stage == "wrong_shape":
                return np.zeros((1, 2, 2)), np.ones((1, 2))
            raise RuntimeError("backend failed to predict")

        pixel_backend.predict = fail
        factory = pixel_backend
    with pytest.raises(InferenceError) as caught:
        predict_test_set(
            package_and_model.model,
            package_and_model.dataset,
            tmp_path / "runs",
            backend_factory=factory,
        )
    record = load_inference_record(caught.value.run_dir)
    assert record["status"] == "failed"
    assert record["error"]
    assert record["processed_frames"] == 0
    assert socket.getaddrinfo is old_getaddrinfo
    assert dict(os.environ) == old_environment


def test_interrupt_is_preserved_and_recorded(package_and_model, pixel_backend, tmp_path):
    def interrupt(self, images):
        raise KeyboardInterrupt

    pixel_backend.predict = interrupt
    with pytest.raises(KeyboardInterrupt):
        predict_test_set(
            package_and_model.model,
            package_and_model.dataset,
            tmp_path / "runs",
            backend_factory=pixel_backend,
        )
    record = load_inference_record(next((tmp_path / "runs").iterdir()))
    assert record["status"] == "failed"
    assert "KeyboardInterrupt" in record["error"]


@pytest.mark.parametrize("key,value", [("maze_config_id", 8), ("dataset_id", "another-dataset")])
def test_test_inference_requires_models_original_dataset_and_montage(
    package_and_model, pixel_backend, tmp_path, key, value
):
    path = package_and_model.model / "manifest.json"
    model = json.loads(path.read_text(encoding="utf-8"))
    model[key] = value
    write_json(path, model)
    with pytest.raises(InferenceError, match="conjunto congelado|conjunto de origem"):
        predict_test_set(
            package_and_model.model,
            package_and_model.dataset,
            tmp_path / "runs",
            backend_factory=pixel_backend,
        )
    assert not pixel_backend.initialized


@pytest.mark.parametrize("artifact", ["weights", "image"])
def test_corrupted_inputs_are_rejected_before_backend(
    package_and_model, pixel_backend, tmp_path, artifact
):
    path = (
        package_and_model.model / "sleap/best.ckpt"
        if artifact == "weights"
        else package_and_model.dataset / package_and_model.manifest["frames"][-1]["image_path"]
    )
    path.write_bytes(b"CORRUPTED UNIT TEST ARTIFACT")
    with pytest.raises(InferenceError, match="alterado"):
        predict_test_set(
            package_and_model.model,
            package_and_model.dataset,
            tmp_path / "runs",
            backend_factory=pixel_backend,
        )
    assert not pixel_backend.initialized


def test_model_change_during_inference_cannot_be_reported_as_success(
    package_and_model, pixel_backend, tmp_path
):
    original_predict = pixel_backend.predict

    def corrupt_model(self, images):
        (package_and_model.model / "sleap/best.ckpt").write_bytes(b"changed during inference")
        return original_predict(self, images)

    pixel_backend.predict = corrupt_model
    with pytest.raises(InferenceError, match="alterado") as caught:
        predict_test_set(
            package_and_model.model,
            package_and_model.dataset,
            tmp_path / "runs",
            backend_factory=pixel_backend,
        )
    assert load_inference_record(caught.value.run_dir)["status"] == "failed"


def test_duration_includes_csv_writes_and_output_hashing(
    package_and_model, video_inputs, pixel_backend, tmp_path, monkeypatch
):
    clock = {"seconds": 0.0}
    real_hash = inference.file_sha256

    def timed_hash(path):
        if Path(path).name == "pose.csv":
            assert len(_read_csv(path)) == 3  # arquivo completo já fechado quando medido
            clock["seconds"] += 100.0
        return real_hash(path)

    monkeypatch.setattr(inference.time, "perf_counter", lambda: clock["seconds"])
    monkeypatch.setattr(inference, "file_sha256", timed_hash)
    run = infer_trial(
        package_and_model.model,
        output_root=tmp_path / "runs",
        **video_inputs,
        backend_factory=pixel_backend,
    )
    assert load_inference_record(run, verify=False)["duration_seconds"] == 100.0


def test_record_verifies_output_hashes_but_allows_later_receipts(
    package_and_model, pixel_backend, tmp_path
):
    _, run = predict_test_set(
        package_and_model.model,
        package_and_model.dataset,
        tmp_path / "runs",
        backend_factory=pixel_backend,
    )
    (run / "registro-banco.json").write_text("{}", encoding="utf-8")
    assert load_inference_record(run)["status"] == "completed"
    (run / "predicoes.csv").write_text("alterado", encoding="utf-8")
    with pytest.raises(InferenceError, match="alterado") as caught:
        load_inference_record(run)
    assert caught.value.run_dir == run
    assert load_inference_record(run, verify=False)["status"] == "completed"


def test_record_rejects_escaping_artifact_paths_even_without_hash_verification(
    package_and_model, pixel_backend, tmp_path
):
    _, run = predict_test_set(
        package_and_model.model,
        package_and_model.dataset,
        tmp_path / "runs",
        backend_factory=pixel_backend,
    )
    record = load_inference_record(run)
    record["artifacts"]["../outside.csv"] = "a" * 64
    write_json(run / "execucao.json", record)
    with pytest.raises(InferenceError, match="fora do pacote"):
        load_inference_record(run, verify=False)


def test_adapter_reorders_nodes_and_preserves_invalid_instances(tmp_path, monkeypatch):
    """Contrato da API SLEAP-NN simulado; nenhum peso nem runtime real é carregado."""
    names = ["base_cauda", "focinho", "centro_corpo"]
    coords = np.arange(12, dtype=float).reshape(2, 1, 3, 2)
    values = {
        "pred_keypoints": coords,
        "pred_peak_values": np.ones((2, 1, 3)),
        "instance_valid": np.array([[True], [False]]),
    }
    predictor = SimpleNamespace(
        skeleton=SimpleNamespace(node_names=names),
        predict=Mock(return_value=[SimpleNamespace(numpy=lambda: values)]),
    )
    factory = Mock(return_value=predictor)
    provider = Mock(side_effect=lambda images, **kwargs: images)
    for name in (
        "sleap_nn",
        "sleap_nn.inference",
        "sleap_nn.inference.predictor",
        "sleap_nn.inference.providers",
    ):
        monkeypatch.setitem(sys.modules, name, ModuleType(name))
    sys.modules["sleap_nn.inference.predictor"].Predictor = SimpleNamespace(
        from_model_paths=factory
    )
    sys.modules["sleap_nn.inference.providers"].NumpyProvider = provider
    monkeypatch.setattr(
        inference.importlib.metadata,
        "version",
        lambda package: {
            "sleap-nn": inference.SLEAP_NN_VERSION,
            "sleap-io": inference.SLEAP_IO_VERSION,
        }[package],
    )
    backend = SleapBackend(tmp_path)
    images = np.zeros((2, 32, 48, 3), dtype=np.uint8)
    points, scores = backend.predict(images)
    assert np.array_equal(points[0], coords[0, 0, [1, 2, 0]])
    assert np.isnan(points[1]).all() and np.isnan(scores[1]).all()
    assert factory.call_args.kwargs["peak_threshold"] == 0.0
    assert provider.call_args.args[0] is images
    assert predictor.predict.call_args.kwargs == {"make_labels": False}
    values["pred_keypoints"] = np.zeros((2, 2, 3, 2))
    with pytest.raises(InferenceError, match="um animal"):
        backend.predict(images)


def test_adapter_rejects_wrong_installed_version(tmp_path, monkeypatch):
    monkeypatch.setattr(inference.importlib.metadata, "version", lambda package: "999.0")
    with pytest.raises(InferenceError, match="exige sleap-nn"):
        SleapBackend(tmp_path)
