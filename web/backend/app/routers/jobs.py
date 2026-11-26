"""`GET /api/jobs` (histórico) e `GET /api/jobs/{id}` (status para polling)."""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from rq.exceptions import NoSuchJobError
from rq.job import Job as RQJob

from barnes.db.jobs import get_job, list_recent_jobs

from ..deps import get_db
from ..queue import redis_conn
from ..schemas.jobs import Job, JobDetail

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[Job])
def get_jobs(limit: int = 50, conn: psycopg.Connection = Depends(get_db)) -> list[Job]:
    return [
        Job.model_validate(row, from_attributes=True) for row in list_recent_jobs(conn, limit=limit)
    ]


@router.get("/{job_id}", response_model=JobDetail)
def get_job_endpoint(job_id: int, conn: psycopg.Connection = Depends(get_db)) -> JobDetail:
    """Status durável (tabela `jobs`) + resultado do RQ, se o Redis ainda o tiver.

    O frontend faz polling aqui enquanto `status` for "queued"/"started".
    """
    try:
        record = get_job(conn, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    result = None
    try:
        result = RQJob.fetch(record.rq_job_id, connection=redis_conn).result
    except NoSuchJobError:
        pass  # Redis já expirou o job (result_ttl) — o status da tabela `jobs` continua valendo.

    return JobDetail.model_validate({**record.__dict__, "result": result})
