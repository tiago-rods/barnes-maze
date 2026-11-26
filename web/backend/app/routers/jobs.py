"""`GET /api/jobs` — histórico de jobs em segundo plano (ver `barnes.db.jobs`)."""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends

from barnes.db.jobs import list_recent_jobs

from ..deps import get_db
from ..schemas.jobs import Job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[Job])
def get_jobs(limit: int = 50, conn: psycopg.Connection = Depends(get_db)) -> list[Job]:
    return [
        Job.model_validate(row, from_attributes=True) for row in list_recent_jobs(conn, limit=limit)
    ]
