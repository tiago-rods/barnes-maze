"""Modelo de resposta para `GET /api/executions/{id}` (US-27)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

ExecutionKind = Literal["treino", "avaliacao", "inferencia", "processamento"]
ExecutionStatus = Literal["concluido", "falhou"]


class Execution(BaseModel):
    id: int
    kind: ExecutionKind
    model_id: str | None
    maze_config_id: int
    trial_id: int | None
    status: ExecutionStatus
    duration_seconds: float | None
    artifact_path: str | None
    metadata: dict[str, Any]
    recorded_at: datetime
    git_commit: str | None
    git_dirty: bool | None
    limiares: dict[str, Any] | None
    limiares_sha256: str | None
    parametros: dict[str, Any] | None
    video_hash: str | None
    iniciado_em: datetime | None
    reproducible: bool
