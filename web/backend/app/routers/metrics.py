"""`POST /api/metrics/displacement` — enfileira distância/velocidade a partir da série (US-18)."""

from __future__ import annotations

from fastapi import APIRouter

from ..jobs.metrics_jobs import run_metrics_displacement
from ..jobs.tracking import enqueue_tracked
from ..schemas.jobs import JobEnqueued
from ..schemas.metrics import DisplacementRequest

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.post("/displacement", response_model=JobEnqueued, status_code=202)
def displacement(request: DisplacementRequest) -> JobEnqueued:
    job_id = enqueue_tracked(
        run_metrics_displacement,
        request.model_dump(),
        kind="metrics_displacement",
        trial_id=request.trial_id,
    )
    return JobEnqueued(job_id=job_id)
