"""`GET /api/learning-curves` — curvas descritivas de aprendizado (US-22).

`longitudinal.learning.summarize` já devolve números agregados prontos
para um gráfico interativo (médias por animal/sessão + média±DP entre
animais) — não há agregação nova aqui, só a leitura (`db.learning`) e a
serialização.
"""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query

from barnes.db.learning import load_learning_rows
from barnes.longitudinal.learning import METRICS, summarize

from ..deps import get_db
from ..schemas.learning import LearningCurves, MetricInfo

router = APIRouter(prefix="/api/learning-curves", tags=["learning"])


@router.get("/metrics", response_model=list[MetricInfo])
def list_metrics() -> list[MetricInfo]:
    return [MetricInfo(key=key, label=label) for key, label in METRICS.items()]


@router.get("", response_model=LearningCurves)
def get_learning_curves(
    experiment_id: list[int] | None = Query(None),
    phase: str = "acquisition",
    event: str = "primary",
    metric: str = "latency",
    conn: psycopg.Connection = Depends(get_db),
) -> LearningCurves:
    try:
        rows = load_learning_rows(conn, experiment_ids=experiment_id, phase=phase, event=event)
        result = summarize(rows, metric)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LearningCurves.model_validate(result)
