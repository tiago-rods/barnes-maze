"""Correções manuais de pose ligadas à execução de revisão (US-10 RN05).

`correcao_pose` (migração 0008) guarda um ponto marcado à mão por linha, em
pixels do vídeo original. Como em `trial_results` e `evento_buraco`, a execução
é obrigatória e tem de ser do mesmo trial (FK composta). A execução de revisão
(`kind = 'processamento'`, `parametros.comando = 'pose review'`) é o registro da
intervenção em si: trechos revisados, número de correções, commit e horário.

Não comita a transação.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import psycopg

from barnes.pose.quality import PointCorrection

REVIEW_COMMAND = "pose review"


@dataclass(frozen=True)
class StoredPoseCorrection:
    """Uma correção gravada.

    Attributes:
        id: Id da linha.
        trial_id: Trial corrigido.
        execucao_id: Execução de revisão em que a correção foi feita.
        quadro: Índice do quadro no vídeo.
        ponto: focinho | centro_corpo | base_cauda.
        x_px, y_px: Posição marcada, em pixels do quadro original.
    """

    id: int
    trial_id: int
    execucao_id: int
    quadro: int
    ponto: str
    x_px: float
    y_px: float

    @property
    def correction(self) -> PointCorrection:
        """A correção no formato de `barnes.pose.quality`."""
        return PointCorrection(self.quadro, self.ponto, self.x_px, self.y_px)


def insert_pose_corrections(
    conn: psycopg.Connection,
    *,
    trial_id: int,
    execucao_id: int,
    corrections: Iterable[PointCorrection],
) -> int:
    """Grava as correções de uma sessão de revisão e devolve quantas foram gravadas.

    Raises:
        psycopg.errors.ForeignKeyViolation: Trial ou execução inexistente, ou
            execução de outro trial.
        psycopg.errors.UniqueViolation: Mesmo quadro e ponto duas vezes na
            mesma execução.
    """
    rows = [
        (trial_id, execucao_id, c.frame, c.point, float(c.x_px), float(c.y_px))
        for c in corrections
    ]
    if rows:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO correcao_pose (trial_id, execucao_id, quadro, ponto, x_px, y_px)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
    return len(rows)


def list_pose_corrections(conn: psycopg.Connection, trial_id: int) -> list[StoredPoseCorrection]:
    """Todas as correções do trial, na ordem em que foram registradas.

    Aplicadas nessa ordem (`barnes.pose.quality.apply_corrections`), a da
    revisão mais recente vence para cada quadro e ponto.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, trial_id, execucao_id, quadro, ponto, x_px, y_px
            FROM correcao_pose WHERE trial_id = %s ORDER BY execucao_id, id
            """,
            (trial_id,),
        )
        return [StoredPoseCorrection(*row) for row in cur.fetchall()]


def list_reviewed_ranges(conn: psycopg.Connection, trial_id: int) -> list[tuple[int, int]]:
    """Intervalos de quadros (início, fim, inclusive) já revisados no trial.

    Lidos de `parametros.trechos_revisados` das execuções de revisão. Um trecho
    revisado deixa de ficar pendente mesmo que o operador não tenha corrigido
    nada (por exemplo, animal fora de vista); a cobertura continua mostrando o
    que faltou.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT (r.trecho ->> 'inicio')::INTEGER, (r.trecho ->> 'fim')::INTEGER
            FROM execucao e
            CROSS JOIN LATERAL jsonb_array_elements(
                CASE WHEN jsonb_typeof(e.parametros -> 'trechos_revisados') = 'array'
                     THEN e.parametros -> 'trechos_revisados' ELSE '[]'::JSONB END
            ) WITH ORDINALITY AS r (trecho, posicao)
            WHERE e.trial_id = %s AND e.kind = 'processamento'
              AND e.parametros ->> 'comando' = %s
              AND jsonb_typeof(r.trecho) = 'object'
            ORDER BY e.id, r.posicao
            """,
            (trial_id, REVIEW_COMMAND),
        )
        return [(start, end) for start, end in cur.fetchall()]
