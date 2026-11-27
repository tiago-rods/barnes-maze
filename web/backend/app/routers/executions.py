"""`GET /api/executions/{id}` — proveniência de uma execução (US-27)."""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, HTTPException

from barnes.db.pose_executions import get_execution

from ..deps import get_db
from ..schemas.executions import Execution

router = APIRouter(prefix="/api/executions", tags=["executions"])


@router.get("/{execution_id}", response_model=Execution)
def get_execution_endpoint(
    execution_id: int, conn: psycopg.Connection = Depends(get_db)
) -> Execution:
    try:
        execution = get_execution(conn, execution_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Execution.model_validate(execution, from_attributes=True)
