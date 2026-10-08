"""US-08: avaliação sintética, sem pesos nem dados privados do laboratório."""

import json
import math
from dataclasses import replace

import pytest

from barnes.geometry.holes import generate_holes
from barnes.pose.annotations import KEYPOINTS, AnnotatedFrame
from barnes.pose.dataset import file_sha256
from barnes.pose.evaluation import (
    EvaluationError,
    evaluate_pose,
    finalize_evaluation_record,
    write_evaluation_report,
)
from barnes.pose.split import ManifestRow, SplitLeakageError


def _frame(trial, index, center=(160.0, 120.0), body=20.0):
    x, y = center
    return AnnotatedFrame(trial, index, ((x + body / 2, y), center, (x - body / 2, y)))


def _shift(frame, error):
    return replace(frame, points=tuple((x + error, y) for x, y in frame.points))


@pytest.fixture
def evaluation_data(geometry):
    # Sete centros tornam possível o global passar enquanto a borda reprova.
    frames = [_frame("train", 0), _frame("validation", 0)]
    frames += [_frame("test", index) for index in range(7)]
    frames += [_frame("test", 7, (225.0, 120.0)), _frame("test", 8, (250.0, 120.0))]
    manifest = [ManifestRow("train", 0, "treino"), ManifestRow("validation", 0, "validacao")]
    manifest += [ManifestRow("test", index, "teste") for index in range(9)]
    return frames, list(frames[2:]), manifest, {"test": geometry}


def _evaluate(data, params):
    return evaluate_pose(*data, params)


def test_exact_predictions_pass_each_point_and_region(evaluation_data, region_params):
    report = _evaluate(evaluation_data, region_params)
    assert report["accepted"]
    assert report["global"]["aggregate"]["samples"] == 27
    assert report["regions"]["centro"]["frames"] == 7
    assert report["regions"]["borda"]["frames"] == 1
    assert report["regions"]["buraco"]["frames"] == 1
    assert report["follow_up"] is None
    for region in report["regions"].values():
        assert region["passed"]
        for point in KEYPOINTS:
            assert region["by_keypoint"][point]["median_error_px"] == 0.0


def test_global_pass_cannot_hide_border_failure_and_request_is_local(
    evaluation_data, region_params, tmp_path
):
    frames, predicted, manifest, geometries = evaluation_data
    predicted[7] = _shift(predicted[7], 12.0)
    report = evaluate_pose(frames, predicted, manifest, geometries, region_params)
    assert report["global"]["passed"]
    assert not report["regions"]["borda"]["passed"]
    assert report["regions"]["borda"]["aggregate"]["median_error_px"] == 12.0
    assert report["regions"]["borda"]["aggregate"]["median_error_body_fraction"] == 0.6
    assert not report["accepted"]
    request = report["follow_up"]
    assert request["story"] == "US-06"
    assert request["status"] == "pending_local"
    assert request["frozen_test_trials"] == ["test"]
    assert "novos trials" in request["instructions"][0]
    assert "sem reutilizá-los" in request["instructions"][1]
    outputs = write_evaluation_report(report, tmp_path)
    assert json.loads(outputs["evaluation_json"].read_text(encoding="utf-8")) == report
    assert json.loads(outputs["annotation_request_json"].read_text(encoding="utf-8")) == request
    assert "REPROVADO" in outputs["evaluation_markdown"].read_text(encoding="utf-8")
    assert "nenhum ticket externo" in outputs["annotation_request_markdown"].read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("error", [10.0, 10.001])
def test_threshold_is_strict(evaluation_data, region_params, error):
    frames, predicted, manifest, geometries = evaluation_data
    report = evaluate_pose(
        frames, [_shift(frame, error) for frame in predicted], manifest, geometries, region_params
    )
    assert not report["accepted"]
    assert not report["global"]["passed"]


def test_aggregate_pass_cannot_hide_one_bad_keypoint(evaluation_data, region_params):
    frames, predicted, manifest, geometries = evaluation_data
    predicted = [
        replace(frame, points=((frame.points[0][0] + 12, frame.points[0][1]), *frame.points[1:]))
        for frame in predicted
    ]
    report = evaluate_pose(frames, predicted, manifest, geometries, region_params)
    assert report["global"]["aggregate"]["passed"]
    assert not report["global"]["by_keypoint"]["focinho"]["passed"]
    assert not report["accepted"]


@pytest.mark.parametrize("removed_index,region", [(7, "borda"), (8, "buraco")])
def test_missing_region_never_passes(evaluation_data, region_params, removed_index, region):
    frames, predicted, manifest, geometries = evaluation_data
    frames = [f for f in frames if not (f.trial == "test" and f.frame_index == removed_index)]
    predicted = [f for f in predicted if f.frame_index != removed_index]
    manifest = [r for r in manifest if not (r.trial == "test" and r.frame_index == removed_index)]
    report = evaluate_pose(frames, predicted, manifest, geometries, region_params)
    assert report["global"]["passed"]
    assert report["regions"][region]["frames"] == 0
    assert not report["regions"][region]["passed"]
    assert not report["accepted"]
    if region == "borda":
        assert report["follow_up"]["reason"] == "Teste sem quadros de borda."


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf])
def test_nonfinite_prediction_is_failure_even_if_median_passes(
    evaluation_data, region_params, invalid
):
    frames, predicted, manifest, geometries = evaluation_data
    predicted[0] = replace(predicted[0], points=((invalid, 120), *predicted[0].points[1:]))
    report = evaluate_pose(frames, predicted, manifest, geometries, region_params)
    assert report["global"]["aggregate"]["median_error_body_fraction"] == 0.0
    assert report["global"]["aggregate"]["missing_predictions"] == 1
    assert report["global"]["aggregate"]["samples"] == 27
    assert not report["accepted"]
    json.dumps(report, allow_nan=False)


def test_missing_whole_frame_is_not_dropped(evaluation_data, region_params):
    frames, predicted, manifest, geometries = evaluation_data
    report = evaluate_pose(frames, predicted[:-1], manifest, geometries, region_params)
    metrics = report["regions"]["buraco"]["aggregate"]
    assert metrics["samples"] == metrics["missing_predictions"] == 3
    assert metrics["median_unbounded"]
    assert metrics["median_error_px"] is None
    assert not report["accepted"]
    assert len(report["frame_errors"]) == 9
    json.dumps(report, allow_nan=False)


def test_missing_point_is_not_dropped(evaluation_data, region_params):
    frames, predicted, manifest, geometries = evaluation_data
    predicted[-1] = replace(predicted[-1], points=predicted[-1].points[:2])
    report = evaluate_pose(frames, predicted, manifest, geometries, region_params)
    assert report["regions"]["buraco"]["by_keypoint"]["base_cauda"]["missing_predictions"] == 1
    assert not report["accepted"]


def test_no_predictions_still_reports_all_test_samples(evaluation_data, region_params):
    frames, _, manifest, geometries = evaluation_data
    report = evaluate_pose(frames, [], manifest, geometries, region_params)
    assert not report["accepted"]
    assert report["global"]["aggregate"]["missing_predictions"] == 27
    assert report["global"]["aggregate"]["median_unbounded"]
    json.dumps(report, allow_nan=False)


def test_normalizes_each_frame_before_taking_median(geometry, region_params):
    frames = [_frame("train", 0), _frame("validation", 0)]
    frames += [_frame("test", i, body=body) for i, body in enumerate([10, 100, 10])]
    manifest = [ManifestRow("train", 0, "treino"), ManifestRow("validation", 0, "validacao")]
    manifest += [ManifestRow("test", index, "teste") for index in range(3)]
    predicted = [_shift(frame, error) for frame, error in zip(frames[2:], [4, 40, 6], strict=True)]
    report = evaluate_pose(frames, predicted, manifest, {"test": geometry}, region_params)
    assert report["global"]["aggregate"]["median_error_px"] == 6.0
    assert report["global"]["aggregate"]["median_error_body_fraction"] == pytest.approx(0.4)
    assert report["global"]["passed"]


def test_training_predictions_are_explicitly_ignored(evaluation_data, region_params):
    frames, predicted, manifest, geometries = evaluation_data
    predicted += [_shift(frame, 1000) for frame in frames[:2]]
    report = evaluate_pose(frames, predicted, manifest, geometries, region_params)
    assert report["accepted"]
    assert report["ignored_non_test_predictions"] == 2
    assert report["global"]["frames"] == 9


def test_errors_are_euclidean_in_image_pixels(evaluation_data, region_params):
    frames, predicted, manifest, geometries = evaluation_data
    predicted = [
        replace(frame, points=tuple((x + 3, y + 4) for x, y in frame.points)) for frame in predicted
    ]
    report = evaluate_pose(frames, predicted, manifest, geometries, region_params)
    assert report["global"]["aggregate"]["median_error_px"] == 5.0
    assert report["global"]["aggregate"]["median_error_body_fraction"] == 0.25
    assert report["accepted"]


@pytest.mark.parametrize("invalid", [-1, 0.5, True])
def test_invalid_frame_indexes_are_rejected(evaluation_data, region_params, invalid):
    evaluation_data[1][0] = replace(evaluation_data[1][0], frame_index=invalid)
    with pytest.raises(EvaluationError, match="trial/quadro inválido"):
        _evaluate(evaluation_data, region_params)


@pytest.mark.parametrize("source_index", [0, 1, 2])
def test_duplicate_frames_are_rejected(evaluation_data, region_params, source_index):
    evaluation_data[source_index].append(evaluation_data[source_index][0])
    with pytest.raises(EvaluationError, match="duplicado"):
        _evaluate(evaluation_data, region_params)


def test_trial_leakage_rejected(evaluation_data, region_params):
    frames, predicted, manifest, geometries = evaluation_data
    frames.append(_frame("test", 99))
    manifest.append(ManifestRow("test", 99, "treino"))
    with pytest.raises(SplitLeakageError, match="test"):
        evaluate_pose(frames, predicted, manifest, geometries, region_params)


@pytest.mark.parametrize("change", ["unassigned", "unannotated", "no_validation", "unknown"])
def test_manifest_must_align_completely(evaluation_data, region_params, change):
    frames, predicted, manifest, geometries = evaluation_data
    if change == "unassigned":
        frames.append(_frame("extra", 0))
    elif change == "unannotated":
        manifest.append(ManifestRow("extra", 0, "treino"))
    elif change == "no_validation":
        manifest[1] = replace(manifest[1], subset="treino")
    else:
        manifest[0] = replace(manifest[0], subset="arbitrary")
    with pytest.raises(EvaluationError):
        evaluate_pose(frames, predicted, manifest, geometries, region_params)


def test_prediction_outside_manifest_is_rejected(evaluation_data, region_params):
    evaluation_data[1].append(_frame("unknown", 0))
    with pytest.raises(EvaluationError, match="fora da divisão"):
        _evaluate(evaluation_data, region_params)


def test_zero_length_body_is_rejected(evaluation_data, region_params):
    evaluation_data[0][2] = _frame("test", 0, body=0)
    with pytest.raises(EvaluationError, match="comprimento corporal"):
        _evaluate(evaluation_data, region_params)


def test_nonfinite_ground_truth_is_rejected(evaluation_data, region_params):
    frame = evaluation_data[0][2]
    evaluation_data[0][2] = replace(frame, points=((math.nan, 0), *frame.points[1:]))
    with pytest.raises(EvaluationError, match="coordenada não finita"):
        _evaluate(evaluation_data, region_params)


def test_region_uses_annotated_center_and_each_trials_geometry(evaluation_data, region_params):
    frames, predicted, manifest, geometries = evaluation_data
    shifted = generate_holes(
        center_x_px=225,
        center_y_px=120,
        platform_radius_px=90,
        hole_count=12,
        start_angle_deg=0,
        target_hole_number=0,
        hole_radius_px=8,
    )
    frames.append(_frame("other_test", 0, (225.0, 120.0)))
    manifest.append(ManifestRow("other_test", 0, "teste"))
    geometries["other_test"] = shifted
    # Predição fica em outra região, mas não pode influenciar a classificação.
    predicted.append(_shift(frames[-1], 60))
    report = evaluate_pose(frames, predicted, manifest, geometries, region_params)
    by_frame = {(f["trial"], f["frame_index"]): f for f in report["frame_errors"]}
    assert by_frame["test", 7]["region"] == "borda"
    assert by_frame["other_test", 0]["region"] == "centro"
    assert report["regions"]["centro"]["frames"] == 8


def test_missing_test_geometry_is_rejected(evaluation_data, region_params):
    evaluation_data[3].clear()
    with pytest.raises(EvaluationError, match="Geometria ausente"):
        _evaluate(evaluation_data, region_params)


def test_writer_preserves_previous_report(evaluation_data, region_params, tmp_path):
    report = _evaluate(evaluation_data, region_params)
    paths = write_evaluation_report(report, tmp_path)
    original = paths["evaluation_json"].read_bytes()
    assert "annotation_request_json" not in paths
    with pytest.raises(EvaluationError, match="já existe"):
        write_evaluation_report(report, tmp_path)
    assert paths["evaluation_json"].read_bytes() == original


def test_finalize_evaluation_record_merges_duration_and_hashes_artifacts(tmp_path):
    (tmp_path / "predicoes.csv").write_text("trial,frame_index\n", encoding="utf-8")
    (tmp_path / "registro-banco.json").write_text("{}", encoding="utf-8")
    record = {"status": "completed", "duration_seconds": 1.5}
    finalized = finalize_evaluation_record(tmp_path, record, evaluation_started=0.0)
    assert finalized["prediction_duration_seconds"] == 1.5
    assert finalized["duration_seconds"] >= 0
    assert finalized["artifacts"] == {
        "predicoes.csv": file_sha256(tmp_path / "predicoes.csv"),
    }
    assert "registro-banco.json" not in finalized["artifacts"]
    assert "execucao.json" not in finalized["artifacts"]
    stored = json.loads((tmp_path / "execucao.json").read_text(encoding="utf-8"))
    assert stored == finalized
    # Não muta o dict recebido; o chamador ainda tem o registro original.
    assert "artifacts" not in record
