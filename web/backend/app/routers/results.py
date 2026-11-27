"""`GET /api/trials/{id}/results` — tudo o que a tela de resultados de um trial mostra.

Só leitura, nada calculado aqui: o pipeline (série → eventos → métricas
consolidadas, `jobs/trial_metrics_jobs.py`) já gravou os números; este
endpoint junta o resultado mais recente de `trial_results`, o relatório da
mesma execução (`execucao.metadata.metricas_trial`), o andamento dos jobs do
trial, a geometria da montagem e a trajetória reduzida para o gráfico.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import psycopg
from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import dict_row

from barnes.db.calibration import require_calibration
from barnes.db.jobs import list_jobs_for_trial
from barnes.db.maze_configs import get_maze_config
from barnes.db.trial_results import get_trial_result
from barnes.db.trials import get_trial
from barnes.pose.trajectory import read_trajectory

from ..demo_pose import is_demo_model
from ..deps import get_db
from ..schemas.jobs import Job
from ..schemas.maze import MazeGeometrySchema

router = APIRouter(prefix="/api/trials", tags=["results"])

MAX_TRAJECTORY_POINTS = 600


def _clean(value: Any) -> Any:
    """NaN/inf viram `None` (JSON não os representa)."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(item) for item in value]
    return value


def _trajectory_px(path, cm_per_px: float) -> list[dict[str, float | None]]:
    table = read_trajectory(path)
    columns = {
        name: table.column(name).to_numpy(zero_copy_only=False)
        for name in (
            "t_s",
            "centro_corpo_x_cm_image",
            "centro_corpo_y_cm_image",
            "centro_corpo_valido",
        )
    }
    total = len(columns["t_s"])
    step = max(1, math.ceil(total / MAX_TRAJECTORY_POINTS))
    points = []
    for i in range(0, total, step):
        valid = bool(columns["centro_corpo_valido"][i])
        x = columns["centro_corpo_x_cm_image"][i]
        y = columns["centro_corpo_y_cm_image"][i]
        ok = valid and np.isfinite(x) and np.isfinite(y)
        points.append(
            {
                "t_s": float(columns["t_s"][i]),
                "x_px": float(x / cm_per_px) if ok else None,
                "y_px": float(y / cm_per_px) if ok else None,
            }
        )
    return points


@router.get("/{trial_id}/results")
def get_trial_results(trial_id: int, conn: psycopg.Connection = Depends(get_db)) -> dict:
    try:
        stored = get_trial(conn, trial_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT t.id, t.experiment_id, t.phase, t.day_number, t.trial_number_in_day,
                   t.filename, t.filepath, t.rotation_deg, t.cobertura_pose,
                   e.name AS experiment_name, s.name AS animal_name
            FROM trials t
            JOIN experiments e ON e.id = t.experiment_id
            LEFT JOIN subjects s ON s.experiment_id = t.experiment_id
            WHERE t.id = %s
            """,
            (trial_id,),
        )
        trial = cur.fetchone()
        cur.execute(
            """
            SELECT model_id FROM execucao
            WHERE trial_id = %s AND kind = 'inferencia'
            ORDER BY id DESC LIMIT 1
            """,
            (trial_id,),
        )
        inference = cur.fetchone()
        cur.execute(
            """
            SELECT tr.*, ex.metadata -> 'metricas_trial' AS report
            FROM trial_results tr
            JOIN execucao ex ON ex.id = tr.execucao_id
            WHERE tr.trial_id = %s
            ORDER BY tr.calculated_at DESC NULLS LAST, tr.id DESC
            LIMIT 1
            """,
            (trial_id,),
        )
        latest = cur.fetchone()

    current = get_trial_result(conn, trial_id)
    model_id = inference["model_id"] if inference else None
    results = None
    if latest is not None:
        report = latest.pop("report")
        results = {
            **{key: latest[key] for key in latest if key not in {"calculated_at"}},
            "calculated_at": latest["calculated_at"].isoformat()
            if latest["calculated_at"]
            else None,
            "is_stale": bool(current.is_stale) if current else False,
            "qualidade_pose": current.qualidade_pose.value
            if current and current.qualidade_pose
            else None,
            "report": report,
        }

    geometry = get_maze_config(conn, stored.maze_config_id)
    try:
        cm_per_px = require_calibration(conn, stored.maze_config_id).cm_per_px
    except ValueError:  # montagem sem escala (US-02): sem trajetória em px
        cm_per_px = None
    trajectory = None
    if cm_per_px and stored.trajectory_path and stored.trajectory_path.is_file():
        trajectory = _trajectory_px(stored.trajectory_path, cm_per_px)

    return _clean(
        {
            "trial": {
                **trial,
                "filepath": str(trial["filepath"]) if trial["filepath"] else None,
                "width_px": stored.width_px,
                "height_px": stored.height_px,
                "fps_real": stored.fps_real,
                "cm_per_px": cm_per_px,
                "interval_start_s": stored.interval.start_s if stored.interval else None,
            },
            "model_id": model_id,
            "is_demo": is_demo_model(model_id),
            "jobs": [
                Job.model_validate(job, from_attributes=True).model_dump(mode="json")
                for job in list_jobs_for_trial(conn, trial_id)
            ],
            "results": results,
            "geometry": MazeGeometrySchema.model_validate(
                geometry, from_attributes=True
            ).model_dump(),
            "trajectory": trajectory,
        }
    )
