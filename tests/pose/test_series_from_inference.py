"""O `pose.csv` real de `infer_trial` (US-07/08) vira a série da US-09 sem adaptação.

Usa o mesmo tipo de artefato falso de `tests/pose/test_inference.py` (modelo e
conjunto marcados como "UNIT TEST ONLY", hashes reais) e um backend falso:
não valida SLEAP nem GPU, só o encaixe entre os dois formatos.
"""

from __future__ import annotations

import json
import math
import shutil
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from barnes.io.trim import interval_from_seconds
from barnes.pose import inference
from barnes.pose.annotations import KEYPOINTS, AnnotatedFrame, frame_filename, write_annotations_csv
from barnes.pose.dataset import file_sha256, prepare_dataset, write_json
from barnes.pose.inference import infer_trial, load_inference_record
from barnes.pose.series import build_series, read_pose_csv
from barnes.pose.split import ManifestRow, write_manifest
from barnes.pose.trajectory import read_trajectory, write_trajectory

FPS = 10.0
MISSING_SNOUT_FRAME = 4


@pytest.fixture
def fake_model(tmp_path, monkeypatch):
    monkeypatch.setattr(inference, "environment_record", lambda: {"unit_test_only": True})
    source = tmp_path / "annotation-source"
    frames, split = [], []
    for trial, subset, color in (("111111111111", "treino", 10),
                                 ("222222222222", "validacao", 20),
                                 ("333333333333", "teste", 30)):
        folder = source / trial / "quadros"
        folder.mkdir(parents=True)
        (folder.parent / "amostragem.csv").write_text("maze_config_id\n7\n", encoding="utf-8")
        # PNGs distintos por subconjunto: o preparo recusa imagem repetida entre eles.
        image = np.full((32, 48, 3), color, np.uint8)
        assert cv2.imwrite(str(folder / frame_filename(0)), image)
        frames.append(AnnotatedFrame(trial, 0, ((18.0, 10.0), (10.0, 10.0), (2.0, 10.0))))
        split.append(ManifestRow(trial, 0, subset))
    write_annotations_csv(frames, source / "anotacoes.csv")
    write_manifest(split, source / "divisao.csv")
    dataset = prepare_dataset(
        source / "anotacoes.csv", source / "divisao.csv", source, tmp_path / "packages", 7,
        exporter=lambda selected, root, output: output.write_bytes(b"UNIT TEST ONLY"),
    )
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    model = tmp_path / "unit-only-model"
    (model / "sleap").mkdir(parents=True)
    for relative in ("sleap/best.ckpt", "sleap/training_config.yaml", "config.yaml"):
        (model / relative).write_text("UNIT TEST ONLY", encoding="utf-8")
    shutil.copyfile(dataset / "manifest.json", model / "dataset_manifest.json")
    write_json(model / "manifest.json", {
        "schema_version": 1, "status": "completed", "model_id": "unit-only-model",
        "maze_config_id": 7, "dataset_id": manifest["dataset_id"], "keypoints": list(KEYPOINTS),
        "checkpoint": "sleap/best.ckpt", "config_path": "config.yaml",
        "artifacts": {p.relative_to(model).as_posix(): file_sha256(p)
                      for p in model.rglob("*") if p.is_file()},
    })
    return model


class WalkingBackend:
    """Animal andando para baixo na tela (θ = 90°); o focinho some num quadro."""

    calls = 0

    def __init__(self, model_dir, *, device, batch_size):
        WalkingBackend.calls = 0

    def predict(self, images):
        points, scores = [], []
        for _ in images:
            frame = 2 + WalkingBackend.calls  # o intervalo começa no quadro 2
            WalkingBackend.calls += 1
            y = 4.0 + frame
            snout = (np.nan, np.nan) if frame == MISSING_SNOUT_FRAME else (24.0, y + 8)
            points.append([snout, (24.0, y), (24.0, y - 8)])
            scores.append([np.nan if frame == MISSING_SNOUT_FRAME else 0.9, 0.8, 0.7])
        return np.array(points, dtype=float), np.array(scores, dtype=float)


@pytest.fixture
def video(tmp_path):
    path = tmp_path / "trial.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (48, 32))
    for index in range(10):
        writer.write(np.full((32, 48, 3), index * 20, dtype=np.uint8))
    writer.release()
    return path


def test_inference_output_becomes_contract_series(fake_model, video, tmp_path):
    interval = interval_from_seconds(0.2, 0.7, FPS, manually_adjusted=True)  # quadros 2..7
    run = infer_trial(
        fake_model, video, tmp_path / "runs", trial_id=12, maze_config_id=7, interval=interval,
        expected_content_hash=file_sha256(video), fps=FPS, frame_count=10, width=48, height=32,
        backend_factory=WalkingBackend,
    )
    record = load_inference_record(run)
    frames = record["processed_interval_frames"]

    table = build_series(
        read_pose_csv(run / "pose.csv"), trial_id=12, execucao_id=1,
        expected_frames=(frames["start"], frames["end"]), fps=record["fps"], interval=interval,
        fps_variable=False, cm_per_px=0.5, content_hash=record["content_hash"],
        model_id=record["model_id"],
    )
    path = write_trajectory(table, tmp_path / "trial_12.parquet")
    series = SimpleNamespace(**read_trajectory(path).to_pydict())

    assert series.quadro == [2, 3, 4, 5, 6, 7]
    assert series.t_s == pytest.approx([0.0, 0.1, 0.2, 0.3, 0.4, 0.5])
    assert series.centro_corpo_x_cm_image == pytest.approx([12.0] * 6)  # 24 px · 0,5
    missing = series.quadro.index(MISSING_SNOUT_FRAME)
    assert series.pose_valida[missing] is False and math.isnan(series.theta_deg_image[missing])
    others = [theta for i, theta in enumerate(series.theta_deg_image) if i != missing]
    assert others == pytest.approx([90.0] * 5)  # para baixo na tela = 90° (sentido horário)
