"""`POST /api/events/enter` — enfileira descoberta+entrada por buraco (US-11/12/13)."""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends

from barnes.db.jobs import insert_job

from ..deps import get_db
from ..jobs.events_jobs import run_events_enter
from ..queue import queue
from ..schemas.events import EnterRequest
from ..schemas.jobs import JobEnqueued

router = APIRouter(prefix="/api/events", tags=["events"])


@router.post("/enter", response_model=JobEnqueued, status_code=202)
def enter(request: EnterRequest, conn: psycopg.Connection = Depends(get_db)) -> JobEnqueued:
    rq_job = queue.enqueue(run_events_enter, **request.model_dump())
    job_id = insert_job(conn, rq_job_id=rq_job.id, kind="events_enter", trial_id=request.trial_id)
    return JobEnqueued(job_id=job_id)
