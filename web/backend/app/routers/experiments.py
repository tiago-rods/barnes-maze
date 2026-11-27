"""`GET /api/experiments` (lista) e `POST /api/experiments` (criação) para o wizard web.

A criação usa um usuário "operador local" implícito (`barnes.db.experiments
.ensure_local_user`) — a ferramenta é local e de um único usuário, sem
tela de login/cadastro de usuário.
"""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends

from barnes.db.experiments import insert_experiment, list_experiments

from ..deps import get_db
from ..schemas.experiments import (
    CreateExperimentRequest,
    CreateExperimentResponse,
    ExperimentSummary,
)

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


@router.get("", response_model=list[ExperimentSummary])
def get_experiments(conn: psycopg.Connection = Depends(get_db)) -> list[ExperimentSummary]:
    return [
        ExperimentSummary.model_validate(row, from_attributes=True)
        for row in list_experiments(conn)
    ]


@router.post("", response_model=CreateExperimentResponse)
def create_experiment(
    request: CreateExperimentRequest, conn: psycopg.Connection = Depends(get_db)
) -> CreateExperimentResponse:
    experiment_id = insert_experiment(conn, name=request.name, description=request.description)
    return CreateExperimentResponse(experiment_id=experiment_id)
