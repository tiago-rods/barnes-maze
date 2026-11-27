"""`POST /api/metrics/displacement` — enfileira distância/velocidade a partir da série (US-18)."""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends

from barnes.db.jobs import insert_job

from ..deps import get_db
from ..jobs.metrics_jobs import run_metrics_displacement
from ..queue import queue
from ..schemas.jobs import JobEnqueued
from ..schemas.metrics import DisplacementRequest

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.post("/displacement", response_model=JobEnqueued, status_code=202)
def displacement(
    request: DisplacementRequest, conn: psycopg.Connection = Depends(get_db)
) -> JobEnqueued:
    rq_job = queue.enqueue(run_metrics_displacement, **request.model_dump())
    job_id = insert_job(
        conn, rq_job_id=rq_job.id, kind="metrics_displacement", trial_id=request.trial_id
    )
    return JobEnqueued(job_id=job_id)
