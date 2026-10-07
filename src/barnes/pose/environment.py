"""Inventário local e planejamento de treino, sem acesso à rede (US-07).

RAM usa GB decimal: 16 GB = 16.000.000.000 bytes disponíveis ao sistema
operacional. Isso não recusa uma máquina nominal de 16 GiB apenas pela RAM
reservada ao hardware. VRAM usa a unidade devolvida pelo nvidia-smi: 4096 MiB.
O inventário não importa torch nem garante compatibilidade CUDA do ambiente;
essa compatibilidade deve ser conferida pelo backend antes do treino.
"""

from __future__ import annotations

import csv
import ctypes
import importlib.metadata
import io
import os
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MIN_RAM_BYTES = 16_000_000_000
MIN_GPU_MEMORY_MIB = 4096
NVIDIA_SMI_TIMEOUT_SECONDS = 10
_PACKAGES = ("barnes", "sleap-nn", "sleap-io", "sleap", "torch", "torchvision", "numpy")
_LOCATION_ORDER = ("grupo", "institucional", "kaggle", "colab")


def _physical_memory_bytes() -> int | None:
    """RAM física utilizável pelo SO; None significa leitura indisponível."""
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_uint32),
                ("memory_load", ctypes.c_uint32),
                ("total_phys", ctypes.c_uint64),
                ("avail_phys", ctypes.c_uint64),
                ("total_page_file", ctypes.c_uint64),
                ("avail_page_file", ctypes.c_uint64),
                ("total_virtual", ctypes.c_uint64),
                ("avail_virtual", ctypes.c_uint64),
                ("avail_extended_virtual", ctypes.c_uint64),
            ]

        try:
            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            function = ctypes.WinDLL("kernel32", use_last_error=True).GlobalMemoryStatusEx
            function.argtypes = [ctypes.POINTER(MemoryStatus)]
            function.restype = ctypes.c_int
            return int(status.total_phys) if function(ctypes.byref(status)) else None
        except (AttributeError, OSError):
            return None
    try:
        size = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        return int(size) if size > 0 else None
    except (AttributeError, OSError, ValueError):
        return None


def _find_nvidia_smi() -> str | None:
    executable = shutil.which("nvidia-smi")
    if executable:
        return executable
    if os.name == "nt":
        candidates = (
            Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/nvidia-smi.exe",
            Path(os.environ.get("ProgramFiles", "C:/Program Files"))
            / "NVIDIA Corporation/NVSMI/nvidia-smi.exe",
        )
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return None


def _parse_gpus(output: str) -> list[dict[str, Any]]:
    gpus = []
    for row in csv.reader(io.StringIO(output)):
        if not row:
            continue
        if len(row) != 4:
            raise ValueError("Resposta do nvidia-smi não contém as quatro colunas esperadas.")
        index, name, memory, driver = (value.strip() for value in row)
        gpu_index, memory_mib = int(index), int(memory)
        if gpu_index < 0 or memory_mib <= 0 or not name or not driver:
            raise ValueError("Resposta do nvidia-smi contém GPU incompleta ou inválida.")
        gpus.append({
            "index": gpu_index,
            "name": name,
            "memory_mib": memory_mib,
            "driver_version": driver,
        })
    return gpus


def _package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in _PACKAGES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def inspect_hardware() -> dict[str, Any]:
    """Inspeciona esta máquina, sem downloads e sem importar o backend de pose.

    ``eligible`` significa que a RAM e ao menos uma GPU NVIDIA satisfazem o
    requisito mínimo. Não atesta driver recente ou compatibilidade CUDA: a
    versão observada fica registrada para a validação do ambiente de treino.
    Erros de consulta são evidência ausente, nunca aprovação implícita.
    """
    ram_bytes = _physical_memory_bytes()
    reasons = []
    gpus: list[dict[str, Any]] = []
    executable = _find_nvidia_smi()
    command_error = None
    if executable is None:
        command_error = "nvidia-smi não encontrado nesta máquina."
    else:
        try:
            result = subprocess.run(
                [
                    executable,
                    "--query-gpu=index,name,memory.total,driver_version",
                    "--format=csv,noheader,nounits",
                ],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=NVIDIA_SMI_TIMEOUT_SECONDS,
            )
            gpus = _parse_gpus(result.stdout)
        except subprocess.TimeoutExpired:
            command_error = f"nvidia-smi excedeu {NVIDIA_SMI_TIMEOUT_SECONDS} segundos."
        except (OSError, subprocess.CalledProcessError, ValueError) as exc:
            command_error = f"Falha na consulta nvidia-smi: {exc}"
    if command_error:
        reasons.append(command_error)
    if ram_bytes is None:
        reasons.append("Não foi possível confirmar a quantidade de RAM física.")
    elif ram_bytes < MIN_RAM_BYTES:
        reasons.append("RAM abaixo de 16 GB (16.000.000.000 bytes).")
    gpu_eligible = any(gpu["memory_mib"] >= MIN_GPU_MEMORY_MIB for gpu in gpus)
    if not gpu_eligible:
        reasons.append("Nenhuma GPU NVIDIA confirmada com pelo menos 4096 MiB de VRAM.")
    return {
        "schema_version": 1,
        "inspected_at": datetime.now(UTC).isoformat(),
        "eligible": bool(ram_bytes is not None and ram_bytes >= MIN_RAM_BYTES and gpu_eligible),
        "machine": {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "architecture": platform.machine(),
        },
        "ram_bytes": ram_bytes,
        "gpus": gpus,
        "reasons": reasons,
        "requirements": {
            "minimum_ram_bytes": MIN_RAM_BYTES,
            "minimum_gpu_memory_mib": MIN_GPU_MEMORY_MIB,
            "ram_unit": "GB decimal; RAM física utilizável pelo sistema operacional",
        },
        "nvidia_smi": {"executable": executable, "error": command_error},
        "environment": {"python_executable": sys.executable, "packages": _package_versions()},
        "cuda_driver_compatibility": "não verificada; validar com o backend antes do treino",
    }


def plan_training_location(
    group_reports: list[dict[str, Any]],
    institutional_available: bool | None,
    kaggle_available: bool | None,
    colab_available: bool | None,
    d4_approved: bool = False,
    d4_reference: str | None = None,
) -> dict[str, Any]:
    """Planeja grupo → instituição → Kaggle → Colab sem enviar arquivos.

    O chamador deve reunir os relatórios de todas as máquinas oferecidas.
    Lista vazia/resultado desconhecido e disponibilidade ``None`` indicam
    levantamento pendente; não são prova de indisponibilidade. A seleção de
    instituição/nuvem ainda exige executar o inventário na máquina escolhida.
    Nuvem só pode ser selecionada após resposta D4 favorável e identificada;
    a política permite apenas quadros rotulados, nunca os vídeos originais.
    """
    if not isinstance(group_reports, list) or any(
        not isinstance(report, dict) for report in group_reports
    ):
        raise TypeError("group_reports deve ser uma lista de relatórios de máquinas.")
    availability = (institutional_available, kaggle_available, colab_available)
    if any(value is not None and not isinstance(value, bool) for value in availability):
        raise ValueError("Disponibilidade deve ser true, false ou null (não verificada).")
    if not isinstance(d4_approved, bool):
        raise TypeError("d4_approved deve ser booleano.")
    if d4_reference is not None and not isinstance(d4_reference, str):
        raise TypeError("d4_reference deve ser texto ou null.")
    reference = d4_reference.strip() if d4_reference else None
    result: dict[str, Any] = {
        "status": "pending",
        "location": None,
        "order": list(_LOCATION_ORDER),
        "reasons": [],
        "d4_approved": d4_approved,
        "d4_reference": reference,
        "uploads_performed": False,
        "data_policy": "Nuvem: somente quadros rotulados com D4 favorável; nunca vídeos.",
        "requires_hardware_check": True,
        "requires_runtime_check": True,
    }
    for index, report in enumerate(group_reports):
        if report.get("eligible") is True:
            result.update(
                status="selected", location="grupo", group_report_index=index,
                machine=report.get("machine"), requires_hardware_check=False,
            )
            result["reasons"].append("Máquina do grupo atende aos requisitos de RAM e VRAM.")
            return result
    if not group_reports or any(report.get("eligible") is not False for report in group_reports):
        result["reasons"].append("Concluir o levantamento das máquinas do grupo antes do fallback.")
        return result
    result["reasons"].append("Nenhuma máquina avaliada do grupo atende aos requisitos mínimos.")
    if institutional_available is None:
        result["reasons"].append("Confirmar a disponibilidade da GPU institucional.")
        return result
    if institutional_available:
        result.update(status="selected", location="institucional")
        result["reasons"].append("GPU institucional é a primeira alternativa; verificar hardware nela.")
        return result
    result["reasons"].append("GPU institucional declarada indisponível.")
    if not d4_approved or not reference:
        result["status"] = "blocked"
        result["reasons"].append("Nuvem bloqueada: exige resposta D4 favorável e sua referência.")
        return result
    for location, available in (("kaggle", kaggle_available), ("colab", colab_available)):
        if available is None:
            result["reasons"].append(f"Confirmar a disponibilidade de {location} antes de prosseguir.")
            return result
        if available:
            result.update(status="selected", location=location, allowed_cloud_data="quadros_rotulados")
            result["reasons"].append(f"{location} selecionado com D4 favorável registrado.")
            return result
        result["reasons"].append(f"{location} declarado indisponível.")
    result["status"] = "blocked"
    result["reasons"].append("Nenhuma opção de treino está disponível; não houve envio de dados.")
    return result
