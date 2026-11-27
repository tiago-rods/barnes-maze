"""Leitura e criação de experimentos (`experiments`), para o wizard web.

Criar um experimento pelo `barnes` CLI continua responsabilidade dos
scripts em `database/seeds/*.py` — nenhum `barnes` command faz isso. O
wizard web passou a precisar criar experimentos pelo próprio passo
"carregar vídeo" (decisão de escopo revista), por isso `insert_experiment`
mora aqui: é a única exceção.
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


def ensure_local_user(conn: psycopg.Connection) -> int:
    """Garante um usuário "operador local" e devolve seu id.

    `experiments.user_id` é obrigatório no esquema (proveniência), mas o
    wizard web é uma ferramenta local de um único usuário, sem login — não
    existe tela para escolher ou cadastrar um usuário. Reaproveita a
    primeira linha de `users` se já existir uma (ex.: criada por um seed ou
    por uma sessão anterior do wizard); cria uma só na primeira vez.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users ORDER BY id LIMIT 1")
        row = cur.fetchone()
        if row is not None:
            return row[0]
        cur.execute(
            "INSERT INTO users (email, name) VALUES (%s, %s) RETURNING id",
            ("operador-local@barnes.local", "Operador local"),
        )
        return cur.fetchone()[0]


def insert_experiment(
    conn: psycopg.Connection, *, name: str, description: str | None = None
) -> int:
    """Cria um experimento, usando o operador local como usuário (`ensure_local_user`).

    Não comita a transação — quem chama decide quando persistir.
    """
    user_id = ensure_local_user(conn)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO experiments (user_id, name, description) VALUES (%s, %s, %s) RETURNING id",
            (user_id, name, description),
        )
        return cur.fetchone()[0]
