"""`GET /api/trials/{id}` — leitura de um trial já carregado.

`POST /api/trials` — enfileira o carregamento (US-01/03/05); roda no
worker RQ via `app.jobs.video_jobs.run_load_trial`.
"""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, HTTPException

from barnes.db.trials import get_trial, set_trial_rotation

from ..deps import get_db
from ..jobs.tracking import enqueue_tracked
from ..jobs.video_jobs import run_load_trial
from ..schemas.jobs import JobEnqueued
from ..schemas.trials import LoadTrialRequest, SetRotationRequest, Trial

router = APIRouter(prefix="/api/trials", tags=["trials"])


@router.get("/{trial_id}", response_model=Trial)
def get_trial_endpoint(trial_id: int, conn: psycopg.Connection = Depends(get_db)) -> Trial:
    try:
        trial = get_trial(conn, trial_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Trial.model_validate(trial, from_attributes=True)


@router.post("", response_model=JobEnqueued, status_code=202)
def load_trial(request: LoadTrialRequest) -> JobEnqueued:
    """Enfileira o carregamento; devolve o job para polling em `GET /api/jobs/{id}`."""
    job_id = enqueue_tracked(run_load_trial, request.model_dump(), kind="video_load", trial_id=None)
    return JobEnqueued(job_id=job_id)


@router.post("/{trial_id}/rotation", status_code=204)
def set_rotation(
    trial_id: int, request: SetRotationRequest, conn: psycopg.Connection = Depends(get_db)
) -> None:
    try:
        set_trial_rotation(conn, trial_id, request.rotation_deg)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
