"""Validação de integridade, vazamento e pacote portátil US-07."""

import json

import cv2
import numpy as np
import pytest

from barnes.pose.dataset import DatasetError, load_dataset_manifest, prepare_dataset
from barnes.pose.split import SplitLeakageError


def test_frozen_content_version_changes_with_labels_and_pixels(dataset_inputs, fake_exporter):
    inputs = dataset_inputs
    first = prepare_dataset(**inputs, exporter=fake_exporter)
    assert first == prepare_dataset(**inputs, exporter=fake_exporter)
    manifest = load_dataset_manifest(first)
    assert manifest["maze_config_id"] == 7
    assert manifest["subsets"]["teste"] == {"frames": 1, "trials": 1}
    original = inputs["frames_dir"] / "000000000001/quadros/quadro_000005.png"
    cv2.imwrite(str(original), np.full((32, 40, 3), 99, dtype=np.uint8))
    second = prepare_dataset(**inputs, exporter=fake_exporter)
    assert second != first
    assert load_dataset_manifest(first)["dataset_id"] == manifest["dataset_id"]
    csv = inputs["annotations_path"]
    csv.write_text(csv.read_text().replace("10.00", "11.00"), encoding="utf-8")
    third = prepare_dataset(**inputs, exporter=fake_exporter)
    assert third != second


@pytest.mark.parametrize("problem", ["missing", "extra", "duplicate", "empty_subset"])
def test_rejects_split_mismatch(dataset_inputs, fake_exporter, problem):
    path = dataset_inputs["split_path"]
    rows = path.read_text().splitlines()
    if problem == "missing":
        rows = rows[:-1]
    elif problem == "extra":
        rows.append("000000000003,6,teste")
    elif problem == "duplicate":
        rows.append(rows[-1])
    else:
        rows[-1] = rows[-1].replace("teste", "treino")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    with pytest.raises(DatasetError):
        prepare_dataset(**dataset_inputs, exporter=fake_exporter)


def test_rejects_trial_leakage(dataset_inputs, fake_exporter):
    path = dataset_inputs["split_path"]
    with path.open("a") as stream:
        stream.write("000000000001,9,teste\n")
    with pytest.raises(SplitLeakageError):
        prepare_dataset(**dataset_inputs, exporter=fake_exporter)


def test_rejects_pixel_identical_leakage(dataset_inputs, fake_exporter):
    root = dataset_inputs["frames_dir"]
    first = root / "000000000001/quadros/quadro_000005.png"
    second = root / "000000000002/quadros/quadro_000005.png"
    second.write_bytes(first.read_bytes())
    with pytest.raises(DatasetError, match="idêntico"):
        prepare_dataset(**dataset_inputs, exporter=fake_exporter)


def test_rejects_wrong_montagem(dataset_inputs, fake_exporter):
    dataset_inputs["maze_config_id"] = 8
    with pytest.raises(DatasetError, match="montagem"):
        prepare_dataset(**dataset_inputs, exporter=fake_exporter)


def test_rejects_corrupt_artifacts(dataset_inputs, fake_exporter):
    path = prepare_dataset(**dataset_inputs, exporter=fake_exporter)
    (path / "treino.pkg.slp").write_bytes(b"changed")
    with pytest.raises(DatasetError, match="alterado"):
        load_dataset_manifest(path)
    with pytest.raises(DatasetError, match="alterado"):
        prepare_dataset(**dataset_inputs, exporter=fake_exporter)


def test_failed_export_preserves_manifest(dataset_inputs):
    def fail(*args):
        raise RuntimeError("export failed")

    with pytest.raises(RuntimeError):
        prepare_dataset(**dataset_inputs, exporter=fail)
    manifests = list(dataset_inputs["output_root"].glob("*/manifest.json"))
    assert len(manifests) == 1
    assert json.loads(manifests[0].read_text())["status"] == "failed"


def test_real_slp_export_is_portable_and_retains_labels(dataset_inputs, tmp_path):
    sio = pytest.importorskip("sleap_io")
    import shutil

    prepared = prepare_dataset(**dataset_inputs)
    moved = tmp_path / "portable"
    shutil.copytree(prepared, moved)
    # Change the source and frozen PNGs: embedded images must remain independent.
    for image in moved.rglob("*.png"):
        image.write_bytes(b"unreadable")
    for subset, intensity in (("treino", 0), ("validacao", 40), ("teste", 80)):
        labels = sio.load_slp(str(moved / f"{subset}.pkg.slp"))
        assert len(labels) == 1
        assert labels.skeletons[0].node_names == ["focinho", "centro_corpo", "base_cauda"]
        np.testing.assert_allclose(labels[0].instances[0].numpy(), [[10, 10], [15, 15], [20, 20]])
        assert np.all(labels[0].video[0] == intensity)
