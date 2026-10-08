"""Persistência de métricas de trial no banco de dados (US-02 RN03/RN05, US-27 RN02).

`trial_results` é a tabela `metrica` do escopo: **uma linha por trial, por
execução**. Toda linha aponta para a execução que a produziu
(`execucao_id NOT NULL`, FK composta com o trial — migração 0007), então
métrica órfã é erro de esquema, não de convenção. Reprocessar acrescenta uma
linha nova em vez de sobrescrever: o resultado antigo continua consultável
junto com a execução (commit, limiares, parâmetros) que o gerou.

"Atual" é a linha mais recente de cada trial. "Obsoleto" continua derivado na
leitura, comparando `calculated_at`/`px_per_10cm_used` contra a escala atual
da montagem (`maze_configs.calibration_date`/`px_per_10cm`), no mesmo
espírito do comentário da 0001 sobre `measured_error_pct` ser validado pela
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
    execucao_id: int


def insert_trial_result(
    conn: psycopg.Connection,
    trial_id: int,
    *,
    execucao_id: int,
    distance_cm: float,
    speed_mean_cm: float,
    route_efficiency: float | None,
    px_per_10cm_used: float,
    calculated_at: datetime,
) -> int:
    """Grava as métricas de um processamento de trial (US-02 RN03, US-27 RN02).

    Não comita a transação: a execução (`barnes.db.executions`) e as métricas
    que ela produziu devem entrar juntas.

    Args:
        conn: Conexão psycopg aberta.
        trial_id: Id do trial processado.
        execucao_id: Execução que produziu estas métricas — obrigatória.
        distance_cm: Distância percorrida, em cm.
        speed_mean_cm: Velocidade média, em cm/s.
        route_efficiency: Razão caminho-ideal/caminho-percorrido, ou `None`
            se nenhuma distância ideal foi informada.
        px_per_10cm_used: Escala da montagem no momento do cálculo —
            congelada aqui para auditoria (US-02 RN05).
        calculated_at: Quando este cálculo foi feito.

    Returns:
        O id da nova linha em `trial_results`.

    Raises:
        psycopg.errors.ForeignKeyViolation: Se o trial não existir, ou se a
            execução não existir ou for de outro trial.
        psycopg.errors.UniqueViolation: Se a execução já tiver métricas.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trial_results (
                trial_id, execucao_id, distance_cm, speed_mean_cm, route_efficiency,
                px_per_10cm_used, calculated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                trial_id,
                execucao_id,
                distance_cm,
                speed_mean_cm,
                route_efficiency,
                px_per_10cm_used,
                calculated_at,
            ),
        )
        return cur.fetchone()[0]


_SELECT_WITH_STALENESS = """
    SELECT tr.id, tr.trial_id, tr.distance_cm, tr.speed_mean_cm, tr.route_efficiency,
           tr.calculated_at,
           (tr.calculated_at IS NULL
               OR tr.calculated_at::date < mc.calibration_date
               OR tr.px_per_10cm_used IS DISTINCT FROM mc.px_per_10cm) AS is_stale,
           tr.execucao_id
    FROM trial_results tr
    JOIN trials t ON t.id = tr.trial_id
    JOIN maze_configs mc ON mc.id = t.maze_config_id
"""

# Mais recente primeiro; `id` desempata cálculos no mesmo instante.
_LATEST_FIRST = " ORDER BY tr.trial_id, tr.calculated_at DESC NULLS LAST, tr.id DESC"


def _row_to_result(row: tuple) -> StoredTrialResult:
    return StoredTrialResult(*row)


def get_trial_result(conn: psycopg.Connection, trial_id: int) -> StoredTrialResult | None:
    """Lê o resultado atual (mais recente) de um trial, com a obsolescência calculada.

    Returns:
        O resultado, ou `None` se o trial ainda não foi processado.
    """
    with conn.cursor() as cur:
        cur.execute(
            _SELECT_WITH_STALENESS + " WHERE tr.trial_id = %s" + _LATEST_FIRST + " LIMIT 1",
            (trial_id,),
        )
        row = cur.fetchone()
    return None if row is None else _row_to_result(row)


def list_trial_results(conn: psycopg.Connection) -> list[StoredTrialResult]:
    """Lista o resultado atual de cada trial processado, com a obsolescência de cada um."""
    query = _SELECT_WITH_STALENESS.replace("SELECT", "SELECT DISTINCT ON (tr.trial_id)", 1)
    with conn.cursor() as cur:
        cur.execute(f"SELECT * FROM ({query}{_LATEST_FIRST}) atual ORDER BY calculated_at")
        rows = cur.fetchall()
    return [_row_to_result(row) for row in rows]


def list_trial_result_history(
    conn: psycopg.Connection, trial_id: int
) -> list[StoredTrialResult]:
    """Todos os resultados já calculados para um trial, do mais recente ao mais antigo.

    Cada um aponta para sua execução (`execucao_id`), de onde saem modelo,
    limiares e commit usados (US-27 Cenário 2).
    """
    with conn.cursor() as cur:
        cur.execute(_SELECT_WITH_STALENESS + " WHERE tr.trial_id = %s" + _LATEST_FIRST, (trial_id,))
        rows = cur.fetchall()
    return [_row_to_result(row) for row in rows]
