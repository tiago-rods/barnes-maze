"""`POST /api/strategy/classify` — enfileira a classificação de estratégia de busca (US-20)."""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends

from barnes.db.jobs import insert_job

from ..deps import get_db
from ..jobs.strategy_jobs import run_strategy_classify
from ..queue import queue
from ..schemas.jobs import JobEnqueued
from ..schemas.strategy import ClassifyRequest

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


@router.post("/classify", response_model=JobEnqueued, status_code=202)
def classify(request: ClassifyRequest, conn: psycopg.Connection = Depends(get_db)) -> JobEnqueued:
    rq_job = queue.enqueue(run_strategy_classify, **request.model_dump())
    job_id = insert_job(
        conn, rq_job_id=rq_job.id, kind="strategy_classify", trial_id=request.trial_id
    )
    return JobEnqueued(job_id=job_id)
