"""`POST /api/strategy/classify` — enfileira a classificação de estratégia de busca (US-20)."""

from __future__ import annotations

from fastapi import APIRouter

from ..jobs.strategy_jobs import run_strategy_classify
from ..jobs.tracking import enqueue_tracked
from ..schemas.jobs import JobEnqueued
from ..schemas.strategy import ClassifyRequest

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


@router.post("/classify", response_model=JobEnqueued, status_code=202)
def classify(request: ClassifyRequest) -> JobEnqueued:
    job_id = enqueue_tracked(
        run_strategy_classify,
        request.model_dump(),
        kind="strategy_classify",
        trial_id=request.trial_id,
    )
    return JobEnqueued(job_id=job_id)
