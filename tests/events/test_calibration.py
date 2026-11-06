"""Validação sintética da ferramenta; estes testes não são uma entrega D3 nem aceite G3."""

import json
import math
import uuid
from dataclasses import FrozenInstanceError, replace

import pytest

from barnes.events import calibration
from barnes.events.calibration import (
    CalibrationError,
    ManualAnnotations,
    ManualEvent,
    blocked_round,
    compare_events,
    load_manual_annotations,
    load_saved_round,
    render_evidence,
    save_round,
)
from barnes.pose.dataset import file_sha256


@pytest.fixture
def document():
    return {
        "schema_version": 1,
        "trial_id": 7,
        "observer": "Observador sintético — somente teste",
        "source": "Fixture sintética; não é entrega do laboratório",
        "delivered_on": "2026-11-03",
        "time_origin": "intervalo_util",
        "events": [
            {"tipo": "descoberta", "hole_number": 0, "t_s": 2.0},
            {"tipo": "descoberta", "hole_number": 1, "t_s": 4.0},
            {"tipo": "entrada", "hole_number": 0, "t_s": 10.0},
            {"tipo": "entrada", "hole_number": 0, "t_s": 20.0},
        ],
    }


@pytest.fixture
def load_document(tmp_path):
    def load(document):
        path = tmp_path / "synthetic-d3.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return load_manual_annotations(path)

    return load


@pytest.fixture
def provenance():
    return {
        "thresholds": {"encontrar": {"distancia_cm": 3, "angulo_graus": 30}, "entrar": None},
        "hashes": {"config_sha256": "a" * 64, "trajectory_sha256": "b" * 64},
        "environment": {"python": "synthetic-unit-test", "machine": "test-machine"},
        "git": {"commit": None, "dirty": True},
    }


def test_load_records_original_delivery_and_file_hash(document, load_document, tmp_path):
    document["video_sha256"] = "AB" * 32
    manual = load_document(document)
    assert manual.trial_id == 7
    assert manual.video_sha256 == "ab" * 32
    assert manual.source_path == str((tmp_path / "synthetic-d3.json").resolve())
    assert manual.source_sha256 == file_sha256(tmp_path / "synthetic-d3.json")
    assert len(manual.events) == 4
    assert isinstance(manual.events, tuple)
    with pytest.raises(FrozenInstanceError):
        manual.trial_id = 9


def test_source_alias_and_implicit_schema_version_supported(document, load_document):
    document["reference"] = document.pop("source")
    del document["schema_version"]
    assert load_document(document).source == document["reference"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("trial_id", True),
        ("trial_id", 0),
        ("trial_id", "7"),
        ("trial_id", 7.0),
        ("observer", "  "),
        ("observer", None),
        ("source", ""),
        ("delivered_on", "2026-02-30"),
        ("delivered_on", "03/11/2026"),
        ("delivered_on", "2026-11-03T10:00:00"),
        ("time_origin", "video_start"),
        ("time_origin", None),
        ("schema_version", True),
        ("schema_version", 2),
        ("video_sha256", "abc"),
        ("events", []),
        ("events", None),
    ],
)
def test_incomplete_or_invalid_d3_is_rejected(document, load_document, field, value):
    document[field] = value
    with pytest.raises(CalibrationError):
        load_document(document)


@pytest.mark.parametrize(
    "field,value",
    [
        ("tipo", "inspection"),
        ("tipo", True),
        ("hole_number", True),
        ("hole_number", -1),
        ("hole_number", 0.0),
        ("t_s", True),
        ("t_s", -0.001),
        ("t_s", "1.2"),
        ("t_s", math.nan),
        ("t_s", math.inf),
        ("t_s", -math.inf),
        ("t_s", 10**400),
    ],
)
def test_invalid_event_values_are_rejected(document, load_document, field, value):
    document["events"][0][field] = value
    with pytest.raises(CalibrationError):
        load_document(document)


def test_conflicting_source_aliases_are_rejected(document, load_document):
    document["reference"] = "different delivery"
    with pytest.raises(CalibrationError, match="entregas diferentes"):
        load_document(document)


def test_duplicate_json_fields_are_rejected(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"trial_id": 7, "trial_id": 8}', encoding="utf-8")
    with pytest.raises(CalibrationError, match="duplicada"):
        load_manual_annotations(path)


def test_missing_d3_file_is_not_replaced_with_synthetic_data(tmp_path):
    with pytest.raises(CalibrationError, match="anotação D3"):
        load_manual_annotations(tmp_path / "not-delivered.json")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "kind,index,time", [("descoberta", 0, 2.0), ("descoberta", 0, 3.0), ("entrada", 2, 10.0)]
)
def test_duplicate_manual_events_rejected(document, load_document, kind, index, time):
    extra = document["events"][index] | {"tipo": kind, "t_s": time}
    document["events"].append(extra)
    with pytest.raises(CalibrationError, match="duplicado"):
        load_document(document)


def test_direct_manual_api_enforces_same_validation(document, load_document):
    manual = load_document(document)
    with pytest.raises(CalibrationError, match="não vazias"):
        replace(manual, events=())
    with pytest.raises(CalibrationError, match="ManualEvent"):
        replace(manual, events=({"tipo": "descoberta", "hole_number": 0, "t_s": 0},))
    with pytest.raises(CalibrationError, match="trial_id"):
        replace(manual, trial_id=True)


def test_discovery_accepts_exact_limits_with_signed_errors(document, load_document):
    manual = load_document(document)
    automatic = [
        {"tipo": "descoberta", "hole_number": 1, "t_s": 3.5},
        {"tipo": "descoberta", "hole_number": 0, "t_s": 2.5},
    ]
    report = compare_events(manual, automatic, kind="descoberta")
    assert report["status"] == "passed" and report["passed"]
    assert report["trial_id"] == 7
    assert report["tolerance_s"] == 0.5
    assert [pair["signed_error_s"] for pair in report["comparisons"]] == [0.5, -0.5]
    assert all(pair["absolute_error_s"] == 0.5 for pair in report["comparisons"])
    assert report["client_approval"] is False


@pytest.mark.parametrize("times,passed", [([10.3, 19.7], True), ([10.300001, 20.0], False)])
def test_entry_decimal_boundary_is_inclusive(document, load_document, times, passed):
    manual = load_document(document)
    automatic = [{"tipo": "entrada", "hole_number": 0, "t_s": time} for time in times]
    report = compare_events(manual, automatic, kind="entrada")
    assert report["tolerance_s"] == 0.3
    assert report["passed"] is passed
    assert [pair["occurrence"] for pair in report["comparisons"]] == [1, 2]


def test_each_event_must_pass_even_if_average_error_is_small(document, load_document):
    manual = load_document(document)
    automatic = [
        {"tipo": "descoberta", "hole_number": 0, "t_s": 2.0},
        {"tipo": "descoberta", "hole_number": 1, "t_s": 4.50001},
    ]
    report = compare_events(manual, automatic, kind="descoberta")
    assert report["status"] == "divergence_review_required"
    assert report["summary"]["outside_tolerance"] == 1
    assert report["summary"]["within_tolerance"] == 1
    assert report["summary"]["max_absolute_error_s"] == pytest.approx(0.50001)
    assert not report["passed"]
    assert "PI" in report["next_action"]


def test_missing_and_unexpected_holes_fail_without_temporal_rematching(document, load_document):
    manual = load_document(document)
    automatic = [
        {"tipo": "descoberta", "hole_number": 0, "t_s": 2},
        {"tipo": "descoberta", "hole_number": 2, "t_s": 4},
    ]
    report = compare_events(manual, automatic, kind="descoberta")
    assert not report["passed"]
    assert report["summary"]["missing_automatic"] == 1
    assert report["summary"]["unexpected_automatic"] == 1
    missing, unexpected = report["comparisons"][1:]
    assert missing["hole_number"] == 1 and missing["automatic_t_s"] is None
    assert unexpected["hole_number"] == 2 and unexpected["manual_t_s"] is None
    assert missing["signed_error_s"] is unexpected["absolute_error_s"] is None


def test_no_automatic_event_is_a_reported_failure(document, load_document):
    report = compare_events(load_document(document), [], kind="descoberta")
    assert not report["passed"]
    assert report["summary"]["missing_automatic"] == 2
    assert report["summary"]["matched_events"] == 0
    assert report["summary"]["max_absolute_error_s"] is None
    json.dumps(report, allow_nan=False)


def test_repeated_entries_use_order_and_keep_missing_occurrence(document, load_document):
    document["events"].append({"tipo": "entrada", "hole_number": 0, "t_s": 30})
    automatic = [
        {"tipo": "entrada", "hole_number": 0, "t_s": 30},
        {"tipo": "entrada", "hole_number": 0, "t_s": 20},
    ]
    report = compare_events(load_document(document), automatic, kind="entrada")
    assert [(pair["manual_t_s"], pair["automatic_t_s"]) for pair in report["comparisons"]] == [
        (10.0, 20.0),
        (20.0, 30.0),
        (30.0, None),
    ]
    assert report["summary"]["outside_tolerance"] == 2
    assert report["summary"]["missing_automatic"] == 1
    assert not report["passed"]


def test_repeated_extra_entry_is_explicit_even_if_all_manual_pairs_pass(document, load_document):
    automatic = [{"tipo": "entrada", "hole_number": 0, "t_s": value} for value in [30, 20, 10]]
    report = compare_events(load_document(document), automatic, kind="entrada")
    assert report["summary"]["within_tolerance"] == 2
    assert report["summary"]["unexpected_automatic"] == 1
    assert report["comparisons"][-1]["occurrence"] == 3
    assert not report["passed"]


def test_one_kind_per_round_without_silently_including_other_kind(document, load_document):
    report = compare_events(load_document(document), document["events"], kind="descoberta")
    assert report["passed"]
    assert report["summary"]["ignored_other_kind_manual"] == 2
    assert report["summary"]["ignored_other_kind_automatic"] == 2
    assert all(pair["tipo"] == "descoberta" for pair in report["comparisons"])


def test_empty_requested_kind_cannot_pass(document, load_document):
    document["events"] = document["events"][:2]
    with pytest.raises(CalibrationError, match="não contém anotações de entrada"):
        compare_events(load_document(document), [], kind="entrada")


@pytest.mark.parametrize(
    "automatic",
    [
        None,
        [{"tipo": "descoberta", "hole_number": 0}],
        [{"tipo": "entrada", "hole_number": 0, "t_s": math.inf}],
        [
            {"tipo": "descoberta", "hole_number": 0, "t_s": 1},
            {"tipo": "descoberta", "hole_number": 0, "t_s": 2},
        ],
        [
            {"tipo": "entrada", "hole_number": 0, "t_s": 1},
            {"tipo": "entrada", "hole_number": 0, "t_s": 1},
        ],
    ],
)
def test_invalid_automatic_events_are_not_silently_dropped(document, load_document, automatic):
    with pytest.raises(CalibrationError):
        compare_events(load_document(document), automatic, kind="descoberta")


def test_rounds_append_uuid_snapshots_without_mutating_inputs(
    document, load_document, provenance, tmp_path
):
    report = compare_events(load_document(document), document["events"], kind="descoberta")
    output = tmp_path / "rounds"
    first_json, first_md = save_round(report, output, provenance=provenance)
    first_bytes = first_json.read_bytes()
    provenance["thresholds"]["encontrar"]["distancia_cm"] = 4
    second_json, second_md = save_round(report, output, provenance=provenance)
    first = json.loads(first_json.read_text(encoding="utf-8"))
    second = json.loads(second_json.read_text(encoding="utf-8"))
    assert uuid.UUID(first["round_id"])
    assert first_json != second_json and first_md != second_md
    assert first_json.read_bytes() == first_bytes
    assert first["provenance"]["thresholds"]["encontrar"]["distancia_cm"] == 3
    assert second["provenance"]["thresholds"]["encontrar"]["distancia_cm"] == 4
    assert first["provenance"]["thresholds"]["entrar"] is None
    assert "round_id" not in report and "created_at" not in report
    evidence = first_md.read_text(encoding="utf-8")
    assert first["round_id"] in evidence
    assert "não concedido" in evidence
    assert "a" * 64 in evidence
    assert "Erro assinado" in evidence and "Erro absoluto" in evidence


def test_collision_cannot_overwrite_any_existing_evidence(
    document, load_document, provenance, tmp_path, monkeypatch
):
    fixed = uuid.UUID("6d942def-77f2-4f29-ae2b-9a858619ec87")
    monkeypatch.setattr(calibration.uuid, "uuid4", lambda: fixed)
    report = compare_events(load_document(document), [], kind="descoberta")
    paths = save_round(report, tmp_path / "rounds", provenance=provenance)
    original = [path.read_bytes() for path in paths]
    with pytest.raises(CalibrationError, match="nenhuma evidência"):
        save_round(report, tmp_path / "rounds", provenance=provenance)
    assert [path.read_bytes() for path in paths] == original


@pytest.mark.parametrize("issue", ["missing_environment", "nan", "unserializable", "status"])
def test_invalid_round_or_provenance_leaves_no_artifact(
    document, load_document, provenance, tmp_path, issue
):
    report = compare_events(load_document(document), [], kind="entrada")
    if issue == "missing_environment":
        del provenance["environment"]
    elif issue == "nan":
        provenance["thresholds"]["test"] = math.nan
    elif issue == "unserializable":
        provenance["hashes"]["wrong"] = object()
    else:
        report["status"] = "passed"
    output = tmp_path / "invalid-rounds"
    with pytest.raises(CalibrationError):
        save_round(report, output, provenance=provenance)
    assert not output.exists()


def test_missing_d3_creates_explicit_blocked_evidence_without_comparison(tmp_path, provenance):
    report = blocked_round(trial_id=None, kind="descoberta")
    assert report["status"] == "blocked_missing_d3"
    assert report["blocked_on"] == ["D3"]
    assert not report["passed"] and not report["client_approval"]
    assert report["comparisons"] == []
    assert report["manual_annotations"] is report["summary"] is None
    json_path, markdown_path = save_round(report, tmp_path / "blocked", provenance=provenance)
    assert json.loads(json_path.read_text(encoding="utf-8"))["trial_id"] is None
    evidence = markdown_path.read_text(encoding="utf-8")
    assert "Bloqueio externo D3" in evidence
    assert "não substituir por anotação improvisada" in evidence


def test_markdown_escapes_observer_metadata(document, load_document):
    document["observer"] = "Observador | teste\nmais texto"
    report = compare_events(load_document(document), document["events"], kind="entrada")
    assert "Observador \\| teste mais texto" in render_evidence(report)


def test_saving_never_grants_client_approval(document, load_document, provenance, tmp_path):
    report = compare_events(load_document(document), document["events"], kind="entrada")
    report["client_approval"] = True
    json_path, _ = save_round(report, tmp_path / "rounds", provenance=provenance)
    assert json.loads(json_path.read_text(encoding="utf-8"))["client_approval"] is False


def test_direct_manual_event_rejects_boolean_fields():
    with pytest.raises(CalibrationError):
        ManualEvent("entrada", True, 1.0)
    with pytest.raises(CalibrationError):
        ManualEvent("entrada", 0, False)
    with pytest.raises(CalibrationError):
        ManualAnnotations(1, "observer", "source", "2026-11-03", "intervalo_util", ())


def test_partial_round_write_is_removed_without_deleting_previous_evidence(
    tmp_path, provenance, monkeypatch
):
    from pathlib import Path

    original_open = Path.open
    sentinel = tmp_path / "previous.md"
    sentinel.write_text("previous", encoding="utf-8")

    def fail_markdown(path, *args, **kwargs):
        if path.suffix == ".md" and args and args[0] == "x":
            raise OSError("simulated disk failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_markdown)
    with pytest.raises(OSError):
        save_round(blocked_round(trial_id=None, kind="descoberta"), tmp_path, provenance=provenance)
    assert list(tmp_path.iterdir()) == [sentinel]


@pytest.mark.parametrize(
    "kind,missing", [("descoberta", False), ("entrada", False), ("entrada", True)]
)
def test_saved_round_revalidates_timestamps_even_after_source_is_moved(
    document, load_document, provenance, tmp_path, kind, missing
):
    manual = load_document(document)
    automatic = [] if missing else document["events"]
    report = compare_events(manual, automatic, kind=kind)
    path, _ = save_round(report, tmp_path / "rounds", provenance=provenance)
    # A evidência preserva os tempos; consultar não exige recuperar um caminho antigo.
    (tmp_path / "synthetic-d3.json").unlink()
    loaded = load_saved_round(path)
    assert loaded["comparisons"] == report["comparisons"]
    assert loaded["passed"] is (not missing)


def test_blocked_and_inconsistent_rounds_remain_readable(
    tmp_path, provenance, document, load_document
):
    blocked = blocked_round(trial_id=None, kind="descoberta")
    path, _ = save_round(blocked, tmp_path / "rounds", provenance=provenance)
    assert load_saved_round(path)["status"] == "blocked_missing_d3"
    report = compare_events(load_document(document), document["events"], kind="entrada")
    report.update(
        passed=False,
        status="divergence_review_required",
        timing_status="passed",
        consistency_issues=["Trial 7, buraco 0: descoberta ausente"],
    )
    path, _ = save_round(report, tmp_path / "rounds", provenance=provenance)
    assert load_saved_round(path)["timing_status"] == "passed"
    assert not load_saved_round(path)["passed"]


@pytest.mark.parametrize("change", ["empty", "uuid", "date", "duplicate_key", "nan", "pairs"])
def test_unreadable_or_corrupt_saved_round_is_a_domain_error(
    tmp_path, provenance, document, load_document, change
):
    report = compare_events(load_document(document), document["events"], kind="entrada")
    path, _ = save_round(report, tmp_path / "rounds", provenance=provenance)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if change == "empty":
        loaded = []
    elif change == "uuid":
        loaded["round_id"] = 9
    elif change == "date":
        loaded["created_at"] = None
    elif change == "nan":
        loaded["provenance"]["thresholds"]["unused"] = float("nan")
    elif change == "pairs":
        loaded["comparisons"] = []
    body = json.dumps(loaded)
    if change == "duplicate_key":
        body = body[:-1] + ', "passed": true}'
    path.write_text(body, encoding="utf-8")
    with pytest.raises(CalibrationError):
        load_saved_round(path)


def test_saving_incorrect_error_cannot_create_evidence(
    document, load_document, provenance, tmp_path
):
    report = compare_events(load_document(document), document["events"], kind="descoberta")
    report["comparisons"][0]["signed_error_s"] = 12
    with pytest.raises(CalibrationError, match="consistente"):
        save_round(report, tmp_path / "invalid", provenance=provenance)
    assert not (tmp_path / "invalid").exists()
