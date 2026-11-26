"""Consulta US-23: sessão, grupo e estratégia (US-20) de cada trial, sem vídeo."""

from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row


def load_strategy_rows(
    conn: Connection, experiment_id: int, *, phase: str = "acquisition"
) -> list[dict[str, Any]]:
    """Sessão, grupo e estratégia atual de cada trial do experimento, na fase dada.

    `search_strategy` vem da linha de `trial_results` mais recente do trial (US-20),
    ou `None` se o trial ainda não foi classificado — nunca inferido como "random".
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT t.id AS trial_id, t.day_number AS session, e.group_label AS grupo,
                   r.search_strategy AS search_strategy
            FROM trials t
            JOIN experiments e ON e.id = t.experiment_id
            LEFT JOIN LATERAL (
                SELECT search_strategy FROM trial_results WHERE trial_id = t.id
                ORDER BY calculated_at DESC NULLS LAST, id DESC LIMIT 1
            ) r ON TRUE
            WHERE t.experiment_id = %s AND t.phase = %s
            ORDER BY t.day_number, t.trial_number_in_day, t.id
            """,
            (experiment_id, phase),
        )
        return cur.fetchall()
