"""Eventos por buraco ligados à execução que os detectou (US-27; consumido pela US-11).

`evento_buraco` (migração 0007) guarda um evento por linha — descoberta (D,
critério C1) ou entrada (E, critério C2) — com quadro, tempo desde o início do
intervalo útil e a execução que o produziu. Como em `trial_results`, a
execução é obrigatória e tem de ser do mesmo trial (FK composta), então um
evento nunca fica sem a proveniência dos limiares que o definiram.

Não comita a transação.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import psycopg

HoleEventKind = Literal["descoberta", "entrada"]


@dataclass(frozen=True)
class HoleEvent:
    """Um evento de buraco gravado.

    Attributes:
        id: Id da linha.
        trial_id: Trial do evento.
        hole_id: `holes.id` do buraco (não o índice 0..N-1).
        execucao_id: Execução que detectou o evento.
        tipo: "descoberta" ou "entrada".
        quadro: Índice do quadro no vídeo.
        t_s: Segundos desde o início do intervalo útil (US-03 RN05).
        distancia_cm: Distância focinho→buraco no evento, se calculada.
        angulo_deg: Ângulo cabeça→buraco no evento, se calculado.
    """

    id: int
    trial_id: int
    hole_id: int
    execucao_id: int
    tipo: HoleEventKind
    quadro: int
    t_s: float
    distancia_cm: float | None
    angulo_deg: float | None


_COLUMNS = "id, trial_id, hole_id, execucao_id, tipo, quadro, t_s, distancia_cm, angulo_deg"


def insert_hole_event(
    conn: psycopg.Connection,
    *,
    trial_id: int,
    hole_id: int,
    execucao_id: int,
    tipo: HoleEventKind,
    quadro: int,
    t_s: float,
    distancia_cm: float | None = None,
    angulo_deg: float | None = None,
) -> int:
    """Grava um evento de buraco e devolve seu id.

    Raises:
        ValueError: Se `tipo` não for "descoberta" ou "entrada".
        psycopg.errors.ForeignKeyViolation: Trial, buraco ou execução
            inexistente, ou execução de outro trial.
        psycopg.errors.CheckViolation: Quadro, tempo, distância ou ângulo
            fora da faixa válida.
    """
    if tipo not in ("descoberta", "entrada"):
        raise ValueError("tipo deve ser 'descoberta' ou 'entrada'.")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO evento_buraco (
                trial_id, hole_id, execucao_id, tipo, quadro, t_s, distancia_cm, angulo_deg
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (trial_id, hole_id, execucao_id, tipo, quadro, t_s, distancia_cm, angulo_deg),
        )
        return cur.fetchone()[0]


def list_hole_events(
    conn: psycopg.Connection, *, trial_id: int, execucao_id: int | None = None
) -> list[HoleEvent]:
    """Eventos de um trial em ordem de tempo; opcionalmente só os de uma execução."""
    where, values = "trial_id = %s", [trial_id]
    if execucao_id is not None:
        where += " AND execucao_id = %s"
        values.append(execucao_id)
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLUMNS} FROM evento_buraco WHERE {where} ORDER BY t_s, id", values
        )
        return [HoleEvent(*row) for row in cur.fetchall()]
