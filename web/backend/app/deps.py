"""Dependências do FastAPI compartilhadas pelos routers."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg

from barnes.db.connection import get_connection


def get_db() -> Iterator[psycopg.Connection]:
    """Abre uma conexão por requisição.

    Mesmo padrão `with get_connection() as conn:` que a CLI já usa: comita
    ao final de uma requisição sem erro, desfaz em caso de exceção. Sem
    pool — concorrência não é um problema real para uma ferramenta local de
    um único usuário.
    """
    with get_connection() as conn:
        yield conn
