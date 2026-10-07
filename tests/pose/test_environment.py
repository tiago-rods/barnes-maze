"""Inventário e ordem de fallback US-07, sem GPU/rede como pré-requisito."""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from barnes.pose import environment
from barnes.pose.environment import inspect_hardware, plan_training_location


@pytest.fixture
def hardware(monkeypatch):
    monkeypatch.setattr(environment, "_physical_memory_bytes", lambda: 16 * 1024**3)
    monkeypatch.setattr(environment, "_find_nvidia_smi", lambda: "nvidia-smi")
    monkeypatch.setattr(environment, "_package_versions", lambda: {"torch": None})
    monkeypatch.setattr(environment.platform, "platform", lambda: "Windows-test")
    monkeypatch.setattr(environment.platform, "node", lambda: "machine-test")
    monkeypatch.setattr(environment.platform, "machine", lambda: "AMD64")
    run = Mock(return_value=SimpleNamespace(stdout="0, NVIDIA Example, 4096, 555.42\n"))
    monkeypatch.setattr(environment.subprocess, "run", run)
    return run


def test_inventory_records_actual_command_and_is_json_serializable(hardware):
    result = inspect_hardware()
    assert result["eligible"] is True
    assert result["reasons"] == []
    assert result["gpus"] == [{
        "index": 0, "name": "NVIDIA Example", "memory_mib": 4096, "driver_version": "555.42",
    }]
    assert result["environment"]["packages"]["torch"] is None
    assert result["machine"]["python"]
    json.dumps(result, allow_nan=False)
    args, kwargs = hardware.call_args
    assert args[0] == [
        "nvidia-smi", "--query-gpu=index,name,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ]
    assert kwargs["timeout"] == 10
    assert kwargs["check"] is True
    assert "shell" not in kwargs


@pytest.mark.parametrize(
    "ram, eligible",
    [(16_000_000_000, True), (15_999_999_999, False), (None, False), (8 * 1024**3, False)],
)
def test_ram_threshold_is_decimal_and_missing_ram_is_not_approved(hardware, monkeypatch, ram, eligible):
    monkeypatch.setattr(environment, "_physical_memory_bytes", lambda: ram)
    report = inspect_hardware()
    assert report["eligible"] is eligible
    assert report["requirements"]["minimum_ram_bytes"] == 16_000_000_000
    if not eligible:
        assert any("RAM" in reason for reason in report["reasons"])


def test_one_large_gpu_is_enough_and_small_gpus_are_not_added_together(hardware):
    hardware.return_value.stdout = "0, NVIDIA A, 2048, 555.42\n1, NVIDIA B, 2048, 555.42\n"
    assert inspect_hardware()["eligible"] is False
    hardware.return_value.stdout += "2, NVIDIA C, 8192, 555.42\n"
    report = inspect_hardware()
    assert report["eligible"] is True
    assert len(report["gpus"]) == 3


def test_absent_nvidia_smi_never_fabricates_gpu(hardware, monkeypatch):
    monkeypatch.setattr(environment, "_find_nvidia_smi", lambda: None)
    report = inspect_hardware()
    assert report["eligible"] is False
    assert report["gpus"] == []
    assert "não encontrado" in report["nvidia_smi"]["error"]
    hardware.assert_not_called()


@pytest.mark.parametrize(
    "failure",
    [
        FileNotFoundError("missing"),
        PermissionError("denied"),
        subprocess.CalledProcessError(1, "nvidia-smi"),
        subprocess.TimeoutExpired("nvidia-smi", 10),
    ],
)
def test_nvidia_smi_failures_are_recorded_as_ineligible(hardware, failure):
    hardware.side_effect = failure
    report = inspect_hardware()
    assert report["eligible"] is False
    assert report["gpus"] == []
    assert report["nvidia_smi"]["error"]


@pytest.mark.parametrize(
    "output",
    ["", "No devices were found", "0, NVIDIA, N/A, 555", "0, NVIDIA, -1, 555", "0, , 4096, 555"],
)
def test_unreadable_or_empty_gpu_listing_cannot_meet_requirement(hardware, output):
    hardware.return_value.stdout = output
    assert inspect_hardware()["eligible"] is False


def test_package_versions_do_not_import_backend(monkeypatch):
    def version(name):
        if name == "sleap-nn":
            return "0.2.0"
        raise environment.importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(environment.importlib.metadata, "version", version)
    result = environment._package_versions()
    assert result["sleap-nn"] == "0.2.0"
    assert result["torch"] is None


def _plan(reports=None, **overrides):
    kwargs = {
        "group_reports": [{"eligible": False}] if reports is None else reports,
        "institutional_available": None,
        "kaggle_available": None,
        "colab_available": None,
    }
    kwargs.update(overrides)
    return plan_training_location(**kwargs)


def test_group_machine_takes_priority_even_without_cloud_approval():
    report = {"eligible": True, "machine": {"hostname": "grupo-pc"}}
    result = _plan([{"eligible": False}, report], institutional_available=True, kaggle_available=True)
    assert result["location"] == "grupo"
    assert result["group_report_index"] == 1
    assert result["machine"] == report["machine"]
    assert result["requires_hardware_check"] is False
    assert result["requires_runtime_check"] is True
    assert result["uploads_performed"] is False


@pytest.mark.parametrize("reports", [[], [{}], [{"eligible": None}], [{"eligible": "false"}]])
def test_unassessed_group_stops_before_fallback(reports):
    result = _plan(reports, institutional_available=True)
    assert result["status"] == "pending"
    assert result["location"] is None
    assert "levantamento" in result["reasons"][-1]


def test_institution_must_be_checked_before_cloud_even_when_d4_is_approved():
    result = _plan(kaggle_available=True, d4_approved=True, d4_reference="D4-2026-10")
    assert result["status"] == "pending"
    assert result["location"] is None
    assert "institucional" in result["reasons"][-1]


def test_institution_is_first_fallback_and_needs_local_inventory():
    result = _plan(institutional_available=True, kaggle_available=True)
    assert result["status"] == "selected"
    assert result["location"] == "institucional"
    assert result["requires_hardware_check"] is True


@pytest.mark.parametrize(
    "approval, reference", [(False, None), (False, "D4"), (True, None), (True, "   ")],
)
def test_cloud_requires_favorable_identified_d4(approval, reference):
    result = _plan(
        institutional_available=False, kaggle_available=True, colab_available=True,
        d4_approved=approval, d4_reference=reference,
    )
    assert result["status"] == "blocked"
    assert result["location"] is None
    assert "D4" in result["reasons"][-1]
    assert result["uploads_performed"] is False


def test_kaggle_takes_priority_over_colab_with_d4():
    result = _plan(
        institutional_available=False, kaggle_available=True, colab_available=True,
        d4_approved=True, d4_reference=" D4-reuniao-2026-10-06 ",
    )
    assert result["status"] == "selected"
    assert result["location"] == "kaggle"
    assert result["d4_reference"] == "D4-reuniao-2026-10-06"
    assert result["allowed_cloud_data"] == "quadros_rotulados"
    assert "nunca vídeos" in result["data_policy"]
    json.dumps(result, allow_nan=False)


def test_colab_requires_kaggle_to_be_declared_unavailable():
    kwargs = {
        "institutional_available": False, "colab_available": True,
        "d4_approved": True, "d4_reference": "D4",
    }
    assert _plan(**kwargs)["status"] == "pending"
    result = _plan(**kwargs, kaggle_available=False)
    assert result["location"] == "colab"


def test_no_location_available_is_blocked_without_uploads():
    result = _plan(
        institutional_available=False, kaggle_available=False, colab_available=False,
        d4_approved=True, d4_reference="D4",
    )
    assert result["status"] == "blocked"
    assert result["location"] is None
    assert result["order"] == ["grupo", "institucional", "kaggle", "colab"]
    assert result["uploads_performed"] is False


@pytest.mark.parametrize(
    "overrides",
    [{"institutional_available": "false"}, {"d4_approved": "true"}, {"d4_reference": True}],
)
def test_strings_cannot_silently_authorize_availability_or_d4(overrides):
    with pytest.raises((TypeError, ValueError)):
        _plan(**overrides)
