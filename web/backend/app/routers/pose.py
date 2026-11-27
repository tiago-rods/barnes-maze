"""`POST /api/pose/infer` e `/series` — enfileiram os jobs de pose (US-07/08/09/10)."""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends

from barnes.db.jobs import insert_job

from ..deps import get_db
from ..jobs.pose_jobs import run_pose_infer, run_pose_series
from ..queue import queue
from ..schemas.jobs import JobEnqueued
from ..schemas.pose import InferRequest, SeriesRequest

router = APIRouter(prefix="/api/pose", tags=["pose"])


@router.post("/infer", response_model=JobEnqueued, status_code=202)
def infer(request: InferRequest, conn: psycopg.Connection = Depends(get_db)) -> JobEnqueued:
    rq_job = queue.enqueue(run_pose_infer, **request.model_dump())
    job_id = insert_job(conn, rq_job_id=rq_job.id, kind="pose_infer", trial_id=request.trial_id)
    return JobEnqueued(job_id=job_id)


@router.post("/series", response_model=JobEnqueued, status_code=202)
def series(request: SeriesRequest, conn: psycopg.Connection = Depends(get_db)) -> JobEnqueued:
    rq_job = queue.enqueue(run_pose_series, **request.model_dump())
    job_id = insert_job(conn, rq_job_id=rq_job.id, kind="pose_series", trial_id=request.trial_id)
    return JobEnqueued(job_id=job_id)
