"""`GET /api/trials/{id}` — leitura de um trial já carregado."""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, HTTPException

from barnes.db.trials import get_trial

from ..deps import get_db
from ..schemas.trials import Trial

router = APIRouter(prefix="/api/trials", tags=["trials"])


@router.get("/{trial_id}", response_model=Trial)
def get_trial_endpoint(trial_id: int, conn: psycopg.Connection = Depends(get_db)) -> Trial:
    try:
        trial = get_trial(conn, trial_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Trial.model_validate(trial, from_attributes=True)
