"""Persistência de métricas de trial no banco de dados (US-02 RN03/RN05).

`trial_results` é 1:1 por trial (`trial_id UNIQUE`); recalibrar e reprocessar
atualiza a linha existente em vez de criar uma nova — não há tabela de
histórico de execuções. "Obsoleto" é derivado na leitura, comparando
`calculated_at`/`px_per_10cm_used` contra a escala atual da montagem
(`maze_configs.calibration_date`/`px_per_10cm`), no mesmo espírito do
comentário já existente na 0001 sobre `measured_error_pct` ser validado pela
aplicação, não pelo banco.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import psycopg


@dataclass(frozen=True)
class StoredTrialResult:
    id: int
    trial_id: int
    distance_cm: float | None
    speed_mean_cm: float | None
    route_efficiency: float | None
    calculated_at: datetime | None
    is_stale: bool


def upsert_trial_result(
    conn: psycopg.Connection,
    trial_id: int,
    *,
    distance_cm: float,
    speed_mean_cm: float,
    route_efficiency: float | None,
    px_per_10cm_used: float,
    calculated_at: datetime,
) -> int:
    """Grava ou atualiza as métricas de um trial (RN03).

    Não comita a transação. `trial_id` é `UNIQUE` em `trial_results`, então
    reprocessar o mesmo trial atualiza a linha existente — campos fora desta
    chamada (ex.: `search_strategy`, de uma história futura) não são tocados.

    Args:
        conn: Conexão psycopg aberta.
        trial_id: Id do trial processado.
        distance_cm: Distância percorrida, em cm.
        speed_mean_cm: Velocidade média, em cm/s.
        route_efficiency: Razão caminho-ideal/caminho-percorrido, ou `None`
            se nenhuma distância ideal foi informada.
        px_per_10cm_used: Escala da montagem no momento do cálculo —
            congelada aqui para auditoria (RN05).
        calculated_at: Quando este cálculo foi feito.

    Returns:
        O id da linha em `trial_results` (nova ou já existente).

    Raises:
        psycopg.errors.ForeignKeyViolation: Se `trial_id` não existir.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trial_results (
                trial_id, distance_cm, speed_mean_cm, route_efficiency,
                px_per_10cm_used, calculated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (trial_id) DO UPDATE SET
                distance_cm = EXCLUDED.distance_cm,
                speed_mean_cm = EXCLUDED.speed_mean_cm,
                route_efficiency = EXCLUDED.route_efficiency,
                px_per_10cm_used = EXCLUDED.px_per_10cm_used,
                calculated_at = EXCLUDED.calculated_at
            RETURNING id
            """,
            (trial_id, distance_cm, speed_mean_cm, route_efficiency, px_per_10cm_used, calculated_at),
        )
        return cur.fetchone()[0]


_SELECT_WITH_STALENESS = """
    SELECT tr.id, tr.trial_id, tr.distance_cm, tr.speed_mean_cm, tr.route_efficiency,
           tr.calculated_at,
           (tr.calculated_at IS NULL
               OR tr.calculated_at::date < mc.calibration_date
               OR tr.px_per_10cm_used IS DISTINCT FROM mc.px_per_10cm) AS is_stale
    FROM trial_results tr
    JOIN trials t ON t.id = tr.trial_id
    JOIN maze_configs mc ON mc.id = t.maze_config_id
"""


def _row_to_result(row: tuple) -> StoredTrialResult:
    return StoredTrialResult(
        id=row[0],
        trial_id=row[1],
        distance_cm=row[2],
        speed_mean_cm=row[3],
        route_efficiency=row[4],
        calculated_at=row[5],
        is_stale=row[6],
    )


def get_trial_result(conn: psycopg.Connection, trial_id: int) -> StoredTrialResult | None:
    """Lê o resultado de um trial, com a obsolescência já calculada.

    Returns:
        O resultado, ou `None` se o trial ainda não foi processado.
    """
    with conn.cursor() as cur:
        cur.execute(_SELECT_WITH_STALENESS + " WHERE tr.trial_id = %s", (trial_id,))
        row = cur.fetchone()
    return None if row is None else _row_to_result(row)


def list_trial_results(conn: psycopg.Connection) -> list[StoredTrialResult]:
    """Lista todos os resultados processados, com a obsolescência de cada um."""
    with conn.cursor() as cur:
        cur.execute(_SELECT_WITH_STALENESS + " ORDER BY tr.calculated_at")
        rows = cur.fetchall()
    return [_row_to_result(row) for row in rows]
