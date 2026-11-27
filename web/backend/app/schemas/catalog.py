"""Modelo de resposta para `GET /api/catalog` (US-27 RN03)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from barnes.db.catalog import Situation
from barnes.io.video import FileStatus
from barnes.pose.quality import PoseQuality


class FileCheck(BaseModel):
    status: FileStatus
    path: Path
    found_at: Path | None
    actual_hash: str | None


class CatalogEntry(BaseModel):
    trial_id: int
    experiment_id: int
    animal: str | None
    sessao: int
    fase: str
    trial_no_dia: int
    filename: str
    filepath: Path
    content_hash: str
    situacao: Situation
    cobertura_pose: float | None
    execucao_id: int | None
    calculado_em: datetime | None
    fps_variavel: bool
    trajetoria: Path | None
    file_size_bytes: int | None
    arquivo: FileCheck | None
    qualidade_pose: PoseQuality | None
