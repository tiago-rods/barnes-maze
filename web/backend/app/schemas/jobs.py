"""Modelo de resposta para `GET /api/jobs`."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

JobKind = Literal[
    "video_load",
    "pose_infer",
    "pose_series",
    "pose_review_save",
    "events_discover",
    "events_enter",
    "metrics_displacement",
    "strategy_classify",
]
JobStatus = Literal["queued", "started", "finished", "failed"]


class Job(BaseModel):
    id: int
    rq_job_id: str
    kind: JobKind
    trial_id: int | None
    status: JobStatus
    execucao_id: int | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobDetail(Job):
    """Mesmos campos de `Job`, mais o resultado do RQ enquanto o Redis o tiver.

    `result` é `None` até o job terminar (ou depois que o Redis expirar o
    resultado via `result_ttl`) — o status/erro em si continua disponível
    (vêm da tabela `jobs`, permanente).
    """

    result: dict[str, Any] | None = None
