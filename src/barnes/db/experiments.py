"""Leitura de experimentos (`experiments`), para seleção no wizard web.

Só leitura, de propósito: criar um experimento continua responsabilidade
dos scripts em `database/seeds/*.py` (ex.: `lnbio_barnes.py`), não deste
módulo — nenhum `barnes` command cria `experiments`/`subjects` hoje, e o
wizard web não muda isso (decisão de escopo da ferramenta web).
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg


@dataclass(frozen=True)
class ExperimentSummary:
    """Uma linha de `experiments`.

    Attributes:
        id: Id do experimento.
        name: Nome do experimento.
        description: Descrição livre, se houver.
        group_label: Rótulo de grupo para estatística (US-25), se definido.
    """

    id: int
    name: str
    description: str | None
    group_label: str | None


def list_experiments(conn: psycopg.Connection) -> list[ExperimentSummary]:
    """Lista os experimentos existentes, do mais recente para o mais antigo."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, name, description, group_label FROM experiments ORDER BY id DESC"
        )
        return [ExperimentSummary(*row) for row in cur.fetchall()]
