"""Modelos para `POST /api/report/...` (US-25/26)."""

from __future__ import annotations

from pydantic import BaseModel


class SetGroupRequest(BaseModel):
    experiment_id: int
    group: str


class ExportTrialsRequest(BaseModel):
    experiment_id: int
    tempo_limite_s: float | None = None
    out_dir: str = "data/processed"
    config: str = "configs/default.yaml"


class ExportProbesRequest(BaseModel):
    experiment_id: int
    out_dir: str = "data/processed"


class Pendencia(BaseModel):
    trial_id: int
    motivo: str


class ExportResult(BaseModel):
    path: str
    count: int
    pendencias: list[Pendencia]
