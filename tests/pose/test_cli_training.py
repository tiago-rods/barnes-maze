"""CLI US-07/08: decisões reais, arquivos locais e backend/banco substituídos."""

from __future__ import annotations

import json
from contextlib import nullcontext
from unittest.mock import Mock

import psycopg
import pytest
from typer.testing import CliRunner

from barnes import cli
from barnes import cli_pose as commands
from barnes.db.pose_executions import StoredInferenceTrial
from barnes.io.trim import interval_from_seconds
from barnes.pose.annotations import AnnotatedFrame
from barnes.pose.dataset import file_sha256
from barnes.pose.inference import InferenceError

runner = CliRunner()


def _json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _hardware(eligible):
    return {
        "eligible": eligible,
        "machine": {"hostname": "local-test"},
        "ram_bytes": 16_000_000_000,
        "gpus": [{"index": 0, "name": "NVIDIA test", "memory_mib": 4096, "driver_version": "555"}]
        if eligible
        else [],
        "reasons": [] if eligible else ["Nenhuma GPU NVIDIA elegível."],
    }


def _run(tmp_path, *, kind="inferencia", status="completed"):
    directory = tmp_path / f"{kind}-unit-test"
    directory.mkdir()
    artifact = "pose.csv" if kind == "inferencia" else "predicoes.csv"
    artifacts = {}
    if status == "completed":
        (directory / artifact).write_text("synthetic test output\n", encoding="utf-8")
        artifacts[artifact] = file_sha256(directory / artifact)
    record = {
        "schema_version": 1,
        "kind": kind,
        "status": status,
        "model_id": "sleap-test",
        "maze_config_id": 7,
        "dataset_id": "dataset-test",
        "duration_seconds": 1.25,
        "artifacts": artifacts,
    }
    if kind == "inferencia":
        record["trial_id"] = 12
    if status == "failed":
        record["error"] = "Falha simulada do backend"
    _json(directory / "execucao.json", record)
    return directory, record


@pytest.fixture
def fake_db(monkeypatch, geometry):
    connection = Mock(side_effect=lambda dsn=None: nullcontext(object()))
    record = Mock(return_value=91)
    monkeypatch.setattr(commands, "get_connection", connection)
    monkeypatch.setattr(commands, "get_maze_config", Mock(return_value=geometry))
    monkeypatch.setattr(commands, "list_executions", Mock(return_value=[]))
    monkeypatch.setattr(commands, "record_execution", record)
    return connection, record


@pytest.fixture
def stored_trial(tmp_path, monkeypatch):
    stored = StoredInferenceTrial(
        12,
        7,
        tmp_path / "registered.mp4",
        "a" * 64,
        25.0,
        100,
        320,
        240,
        interval_from_seconds(0.2, 2.0, 25.0, manually_adjusted=True),
    )
    monkeypatch.setattr(commands, "get_inference_trial", Mock(return_value=stored))
    return stored


def test_pose_help_preserves_us06_and_exposes_training_evaluation_commands():
    result = runner.invoke(cli.app, ["pose", "--help"])
    assert result.exit_code == 0, result.output
    for command in (
        "sample",
        "import-slp",
        "split",
        "check-split",
        "report",
        "hardware",
        "plan-training",
        "prepare-training",
        "train",
        "evaluate",
        "infer",
        "register-run",
    ):
        assert command in result.output


@pytest.mark.parametrize("eligible", [True, False])
def test_hardware_saves_inventory_even_when_machine_is_rejected(tmp_path, monkeypatch, eligible):
    document = _hardware(eligible)
    monkeypatch.setattr(commands, "inspect_hardware", lambda: document)
    out = tmp_path / "machine.json"
    result = runner.invoke(cli.app, ["pose", "hardware", "--out", str(out)])
    assert result.exit_code == (0 if eligible else 1), result.output
    assert json.loads(out.read_text(encoding="utf-8")) == document
    assert "local-test" in result.output
    if not eligible:
        assert "Nenhuma GPU NVIDIA" in result.output


def test_hardware_refuses_overwriting_existing_inventory(tmp_path, monkeypatch):
    monkeypatch.setattr(commands, "inspect_hardware", lambda: _hardware(True))
    out = _json(tmp_path / "machine.json", {"original": True})
    result = runner.invoke(cli.app, ["pose", "hardware", "--out", str(out)])
    assert result.exit_code == 1
    assert json.loads(out.read_text(encoding="utf-8")) == {"original": True}


@pytest.mark.parametrize(
    "options, location, exit_code",
    [
        (["--institutional", "sim", "--kaggle", "sim"], "institucional", 0),
        (["--institutional", "nao", "--kaggle", "sim"], None, 1),
        (
            ["--institutional", "nao", "--kaggle", "sim", "--d4-reference", "D4-favoravel"],
            "kaggle",
            0,
        ),
        (["--kaggle", "sim", "--d4-reference", "D4-favoravel"], None, 1),
    ],
)
def test_plan_records_fallback_order_and_d4_gate(tmp_path, options, location, exit_code):
    inventory = _json(tmp_path / "machine.json", _hardware(False))
    out = tmp_path / "plan.json"
    result = runner.invoke(
        cli.app,
        ["pose", "plan-training", "--report", str(inventory), "--out", str(out), *options],
    )
    assert result.exit_code == exit_code, result.output
    plan = json.loads(out.read_text(encoding="utf-8"))
    assert plan["location"] == location
    assert plan["group_reports"] == [_hardware(False)]
    assert plan["uploads_performed"] is False


def test_prepare_missing_annotation_extra_is_friendly(tmp_path, monkeypatch):
    prepare = Mock(side_effect=ImportError("Instale: uv sync --extra anotacao"))
    monkeypatch.setattr(commands, "prepare_dataset", prepare)
    result = runner.invoke(
        cli.app,
        ["pose", "prepare-training", "--maze-config-id", "7", "--out", str(tmp_path / "data")],
    )
    assert result.exit_code == 1
    assert "uv sync --extra anotacao" in result.output
    assert "Traceback" not in result.output


def test_training_ineligible_machine_blocks_before_dataset_database_and_backend(monkeypatch):
    monkeypatch.setattr(commands, "inspect_hardware", lambda: _hardware(False))
    database, dataset, trainer = Mock(), Mock(), Mock()
    monkeypatch.setattr(commands, "get_connection", database)
    monkeypatch.setattr(commands, "load_dataset_manifest", dataset)
    monkeypatch.setattr(commands, "train_model", trainer)
    result = runner.invoke(cli.app, ["pose", "train", "--dataset", "unread-data"])
    assert result.exit_code == 1
    assert "Treino bloqueado" in result.output
    database.assert_not_called()
    dataset.assert_not_called()
    trainer.assert_not_called()


def test_forged_plan_claim_cannot_skip_institution_priority(tmp_path, monkeypatch):
    plan = _json(
        tmp_path / "forged.json",
        {
            "status": "selected",
            "location": "kaggle",
            "group_reports": [_hardware(False)],
            "availability": {"institucional": True, "kaggle": True, "colab": True},
            "d4_approved": True,
            "d4_reference": "D4-favoravel",
        },
    )
    hardware, trainer = Mock(), Mock()
    monkeypatch.setattr(commands, "inspect_hardware", hardware)
    monkeypatch.setattr(commands, "train_model", trainer)
    result = runner.invoke(
        cli.app,
        [
            "pose",
            "train",
            "--dataset",
            "unused",
            "--location",
            "kaggle",
            "--plan",
            str(plan),
        ],
    )
    assert result.exit_code == 1
    assert "Plano não autoriza" in result.output
    hardware.assert_not_called()
    trainer.assert_not_called()


def test_completed_training_registers_complete_manifest_and_receipt(tmp_path, monkeypatch, fake_db):
    _, record = fake_db
    document = {
        "status": "completed",
        "model_id": "sleap-unit-model",
        "maze_config_id": 7,
        "dataset_id": "dataset-v1",
        "elapsed_seconds": 12.0,
        "hyperparameters": {"seed": 42, "max_epochs": 2},
    }
    run_dir = tmp_path / "models" / document["model_id"]
    _json(run_dir / "manifest.json", document)
    monkeypatch.setattr(commands, "inspect_hardware", lambda: _hardware(True))
    monkeypatch.setattr(commands, "load_dataset_manifest", lambda path: {"maze_config_id": 7})
    monkeypatch.setattr(commands, "load_model_manifest", lambda path: document)
    train = Mock(return_value=run_dir)
    monkeypatch.setattr(commands, "train_model", train)
    result = runner.invoke(cli.app, ["pose", "train", "--dataset", "prepared-package"])
    assert result.exit_code == 0, result.output
    assert "execucao 91" in result.output
    assert train.call_args.args[3]["training_location"] == "grupo"
    registration = record.call_args.kwargs
    assert registration["kind"] == "treino"
    assert registration["model_id"] == document["model_id"]
    assert registration["trial_id"] is None
    assert registration["duration_seconds"] == 12.0
    assert registration["metadata"]["hyperparameters"] == document["hyperparameters"]
    assert (
        json.loads((run_dir / "registro-banco.json").read_text(encoding="utf-8"))["execution_id"]
        == 91
    )


def test_training_can_defer_database_for_institutional_machine(tmp_path, monkeypatch, fake_db):
    connection, record = fake_db
    inventory = _hardware(True)
    monkeypatch.setattr(commands, "inspect_hardware", lambda: inventory)
    monkeypatch.setattr(commands, "load_dataset_manifest", lambda path: {"maze_config_id": 7})
    plan = _json(
        tmp_path / "plan.json",
        {
            "group_reports": [_hardware(False)],
            "availability": {"institucional": True},
        },
    )
    run_dir = tmp_path / "model"
    train = Mock(return_value=run_dir)
    monkeypatch.setattr(commands, "train_model", train)
    result = runner.invoke(
        cli.app,
        [
            "pose",
            "train",
            "--dataset",
            "dataset",
            "--location",
            "institucional",
            "--plan",
            str(plan),
            "--defer-db",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "PENDENTE" in result.output and "register-run" in result.output
    connection.assert_not_called()
    record.assert_not_called()
    train.assert_called_once()
    assert train.call_args.args[3]["database_registration"] == "deferred"


@pytest.mark.parametrize("alternate", [False, True])
def test_inference_passes_registered_identity_and_interval(
    tmp_path,
    monkeypatch,
    fake_db,
    stored_trial,
    alternate,
):
    _, record = fake_db
    run_dir, _ = _run(tmp_path)
    backend = Mock(return_value=run_dir)
    monkeypatch.setattr(commands, "infer_trial", backend)
    arguments = ["pose", "infer", "--model", "model", "--trial", "12"]
    alternate_path = tmp_path / "renamed.mp4"
    if alternate:
        arguments.extend(["--video", str(alternate_path)])
    result = runner.invoke(cli.app, arguments)
    assert result.exit_code == 0, result.output
    assert backend.call_args.args[1] == (alternate_path if alternate else stored_trial.filepath)
    context = backend.call_args.kwargs
    assert context["expected_content_hash"] == stored_trial.content_hash
    assert context["interval"] == stored_trial.interval
    assert context["maze_config_id"] == 7
    assert context["fps"] == 25.0
    assert (context["width"], context["height"], context["frame_count"]) == (320, 240, 100)
    assert record.call_args.kwargs["trial_id"] == 12
    assert "1.250s" in result.output


def test_failed_inference_keeps_failure_manifest_and_registers_failure(
    tmp_path,
    monkeypatch,
    fake_db,
    stored_trial,
):
    _, record = fake_db
    run_dir, document = _run(tmp_path, status="failed")
    monkeypatch.setattr(
        commands,
        "infer_trial",
        Mock(side_effect=InferenceError("backend falhou", run_dir=run_dir)),
    )
    result = runner.invoke(cli.app, ["pose", "infer", "--model", "model", "--trial", "12"])
    assert result.exit_code == 1
    assert "backend falhou" in result.output
    assert record.call_args.kwargs["status"] == "falhou"
    assert record.call_args.kwargs["metadata"]["error"] == document["error"]
    assert (run_dir / "execucao.json").exists()


def test_database_outage_preserves_output_and_register_run_recovers_without_inference(
    tmp_path,
    monkeypatch,
    fake_db,
    stored_trial,
):
    _, record = fake_db
    run_dir, document = _run(tmp_path)
    backend = Mock(return_value=run_dir)
    monkeypatch.setattr(commands, "infer_trial", backend)
    record.side_effect = psycopg.OperationalError("banco indisponível")
    failed = runner.invoke(cli.app, ["pose", "infer", "--model", "model", "--trial", "12"])
    assert failed.exit_code == 1
    assert "register-run" in failed.output
    assert file_sha256(run_dir / "pose.csv") == document["artifacts"]["pose.csv"]
    assert not (run_dir / "registro-banco.json").exists()
    record.side_effect = None
    recovered = runner.invoke(
        cli.app, ["pose", "register-run", str(run_dir), "--kind", "inferencia"]
    )
    assert recovered.exit_code == 0, recovered.output
    backend.assert_called_once()
    assert (
        json.loads((run_dir / "registro-banco.json").read_text(encoding="utf-8"))["execution_id"]
        == 91
    )


@pytest.mark.parametrize("all_regions_bad", [False, True])
def test_evaluation_rejection_persists_global_regions_and_border_followup(
    tmp_path,
    monkeypatch,
    fake_db,
    all_regions_bad,
):
    _, record = fake_db
    run_dir, _ = _run(tmp_path, kind="teste")
    centers = [(160.0, 120.0), (227.6, 138.1), (250.0, 120.0)]
    frames, predictions = [], []
    for index, (x, y) in enumerate(centers):
        points = ((x - 10, y), (x, y), (x + 10, y))
        frames.append(
            {"trial": "heldout", "frame_index": index, "points": points, "subset": "teste"}
        )
        shift = 20.0 if all_regions_bad or index == 1 else 0.0
        predictions.append(
            AnnotatedFrame("heldout", index, tuple((px + shift, py) for px, py in points))
        )
    for subset in ("treino", "validacao"):
        frames.append(
            {
                "trial": subset,
                "frame_index": 0,
                "points": ((150, 120), (160, 120), (170, 120)),
                "subset": subset,
            }
        )
    package = {"maze_config_id": 7, "dataset_id": "dataset-test", "frames": frames}
    monkeypatch.setattr(commands, "load_dataset_manifest", lambda path: package)
    monkeypatch.setattr(
        commands,
        "load_model_manifest",
        lambda path: {
            "model_id": "sleap-test",
            "dataset_id": "dataset-test",
        },
    )
    monkeypatch.setattr(commands, "predict_test_set", Mock(return_value=(predictions, run_dir)))
    result = runner.invoke(
        cli.app, ["pose", "evaluate", "--model", "model", "--dataset", "dataset"]
    )
    assert result.exit_code == 1, result.output
    assert "Qualidade REPROVADA" in result.output
    report = json.loads((run_dir / "avaliacao.json").read_text(encoding="utf-8"))
    assert report["accepted"] is False
    assert report["global"]["passed"] is (not all_regions_bad)
    assert report["regions"]["borda"]["passed"] is False
    assert set(report["regions"]) == {"centro", "borda", "buraco"}
    assert (run_dir / "us06-borda.md").is_file()
    assert (run_dir / "avaliacao.md").is_file()
    assert record.call_args.kwargs["kind"] == "avaliacao"
    assert record.call_args.kwargs["status"] == "concluido"
    assert record.call_args.kwargs["metadata"]["evaluation"] == report


@pytest.mark.parametrize(
    "args",
    [
        ["train"],
        ["infer", "--model", "model"],
        ["evaluate", "--model", "model"],
        ["prepare-training"],
        ["plan-training"],
        ["register-run", "run"],
        ["infer", "--model", "model", "--trial", "0"],
        ["evaluate", "--model", "model", "--dataset", "dataset", "--batch-size", "0"],
    ],
)
def test_required_options_and_numeric_limits_are_parsed_before_work(monkeypatch, args):
    database = Mock()
    monkeypatch.setattr(commands, "get_connection", database)
    result = runner.invoke(cli.app, ["pose", *args])
    assert result.exit_code == 2, result.output
    database.assert_not_called()
