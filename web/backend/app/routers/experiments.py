"""`GET /api/experiments` — lista para seleção no wizard (sem criação, ver `barnes.db.experiments`)."""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends

from barnes.db.experiments import list_experiments

from ..deps import get_db
from ..schemas.experiments import ExperimentSummary

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


@router.get("", response_model=list[ExperimentSummary])
def get_experiments(conn: psycopg.Connection = Depends(get_db)) -> list[ExperimentSummary]:
    return [
        ExperimentSummary.model_validate(row, from_attributes=True)
        for row in list_experiments(conn)
    ]
