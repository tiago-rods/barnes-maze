"""`GET /api/experiments` (lista) e `POST /api/experiments` (criação) para o wizard web.

A criação usa um usuário "operador local" implícito (`barnes.db.experiments
.ensure_local_user`) — a ferramenta é local e de um único usuário, sem
tela de login/cadastro de usuário.
"""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, HTTPException

from barnes.db.experiments import insert_experiment, insert_subject, list_experiments

from ..deps import get_db
from ..schemas.experiments import (
    CreateExperimentRequest,
    CreateExperimentResponse,
    CreateSubjectRequest,
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
    experiment_id = insert_experiment(
        conn,
        name=request.name,
        description=request.description,
        animal_name=(request.animal_name or "").strip() or None,
    )
    return CreateExperimentResponse(experiment_id=experiment_id)


@router.post("/{experiment_id}/subject", status_code=204)
def create_subject(
    experiment_id: int, request: CreateSubjectRequest, conn: psycopg.Connection = Depends(get_db)
) -> None:
    """Cadastra o animal de um experimento que ainda não tem (necessário para a US-22)."""
    if not request.name.strip():
        raise HTTPException(status_code=400, detail="Informe o nome do animal.")
    try:
        insert_subject(
            conn, experiment_id=experiment_id, name=request.name.strip(), genotype=request.genotype
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
