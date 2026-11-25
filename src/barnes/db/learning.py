"""Consulta US-22: um snapshot SQL, sem acesso a vídeos ou trajetórias."""

from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row


def load_learning_rows(
    conn: Connection,
    *,
    experiment_ids: list[int] | None = None,
    phase: str = "acquisition",
    event: str = "primary",
) -> list[dict[str, Any]]:
    """Lê o resultado mais recente por trial, sem combinar execuções parciais.

    Sessão é day_number dentro da fase. Vários experimentos permitem vários
    animais (subjects é 1:1 com experiments). NULL nunca significa sucesso.
    """
    if phase not in {"acquisition", "habituation", "probe"}:
        raise ValueError("Fase inválida.")
    if event not in {"primary", "total"}:
        raise ValueError("Evento deve ser primary ou total.")
    if experiment_ids is not None and (not experiment_ids or any(i < 1 for i in experiment_ids)):
        raise ValueError("Informe IDs positivos de experimentos.")
    # Identificadores interpolados pertencem exclusivamente à lista acima.
    query = f"""
        SELECT t.id AS trial_id, t.experiment_id, s.id AS animal_id,
               s.name AS animal_name, t.day_number AS session, t.phase,
               r.id AS result_id, r.execucao_id,
               r.{event}_latency_s AS latency, r.{event}_errors AS errors,
               r.distance_cm AS distance, r.entropy_bits AS entropy,
               r.{event}_event AS observed,
               (r.calculated_at IS NULL OR mc.calibration_date IS NULL
                OR r.calculated_at::date < mc.calibration_date
                OR r.px_per_10cm_used IS DISTINCT FROM mc.px_per_10cm) AS stale,
               e.model_id, e.git_commit, e.git_dirty, e.limiares, e.limiares_sha256,
               e.parametros, qp.qualidade AS pose_quality
        FROM trials t
        JOIN subjects s ON s.experiment_id = t.experiment_id
        JOIN maze_configs mc ON mc.id = t.maze_config_id
        LEFT JOIN LATERAL (
            SELECT * FROM trial_results WHERE trial_id = t.id
            ORDER BY calculated_at DESC NULLS LAST, id DESC LIMIT 1
        ) r ON TRUE
        LEFT JOIN execucao e ON e.id = r.execucao_id AND e.trial_id = t.id
        LEFT JOIN qualidade_pose qp ON qp.trial_id = t.id
        WHERE t.phase = %s
    """
    params = [phase]
    if experiment_ids is not None:
        query += " AND t.experiment_id = ANY(%s)"
        params.append(list(experiment_ids))
    query += " ORDER BY s.id, t.day_number, t.trial_number_in_day, t.id"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        return cur.fetchall()
