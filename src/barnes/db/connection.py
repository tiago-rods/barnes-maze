"""Conexão com o PostgreSQL e aplicação de migrações SQL versionadas."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
from dotenv import find_dotenv, load_dotenv
from psycopg.conninfo import conninfo_to_dict

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "database" / "migrations"

CONNECT_TIMEOUT_S = 10
"""Tempo máximo para abrir a conexão. Sem ele, uma porta sem resposta trava o comando."""


class DatabaseConfigError(Exception):
    """Erro de configuração de conexão com o banco de dados."""


class DatabaseUnavailableError(DatabaseConfigError, psycopg.OperationalError):
    """Não foi possível abrir a conexão (banco fora do ar, porta errada, credenciais).

    É também um `psycopg.OperationalError`, para que quem já trata o banco
    indisponível (ex.: `pose` preservando os artefatos) continue funcionando.
    A mensagem nunca contém a string de conexão nem a senha.
    """


def load_local_env() -> None:
    """Carrega o `.env` do diretório atual (ou acima), sem sobrescrever o terminal.

    O `.env` não é commitado (ver `.env.example`). Uma variável já definida no
    ambiente — inclusive vazia, como os testes fazem para isolar o banco de
    desenvolvimento — tem precedência sobre o arquivo.
    """
    load_dotenv(find_dotenv(usecwd=True), override=False)


def get_connection(dsn: str | None = None) -> psycopg.Connection:
    """Abre uma conexão com o PostgreSQL.

    Args:
        dsn: String de conexão no formato aceito pelo psycopg
            (ex.: ``postgresql://usuario:senha@localhost:5432/barnes``).
            Se omitida, usa a variável de ambiente ``BARNES_DATABASE_URL``,
            lida também do `.env` local (`load_local_env`).

    A conexão desiste depois de `CONNECT_TIMEOUT_S` segundos, a menos que o
    DSN traga o próprio ``connect_timeout``.

    Returns:
        Uma conexão psycopg aberta.

    Raises:
        DatabaseConfigError: Se nenhum DSN foi passado e a variável de
            ambiente também não está definida.
        DatabaseUnavailableError: Se a conexão não pôde ser aberta.
    """
    if not dsn:
        load_local_env()
    dsn = dsn or os.environ.get("BARNES_DATABASE_URL")
    if not dsn:
        raise DatabaseConfigError(
            "Defina a variável de ambiente BARNES_DATABASE_URL ou passe o "
            "DSN explicitamente (ex.: postgresql://usuario:senha@localhost:5433/barnes)."
        )
    params = conninfo_to_dict(dsn)
    extra = {} if "connect_timeout" in params else {"connect_timeout": CONNECT_TIMEOUT_S}
    try:
        return psycopg.connect(dsn, **extra)
    except psycopg.OperationalError as exc:
        raise DatabaseUnavailableError(_unavailable_message(params)) from exc


def _unavailable_message(params: dict) -> str:
    """Mensagem de falha de conexão com host, porta e banco — nunca usuário ou senha."""
    host = params.get("host") or "localhost"
    port = params.get("port") or "5432"
    dbname = params.get("dbname") or "(padrão)"
    timeout = params.get("connect_timeout", CONNECT_TIMEOUT_S)
    return (
        f"Não foi possível conectar ao banco '{dbname}' em {host}:{port} "
        f"(limite de {timeout} s). Confira se o Postgres está rodando "
        "(docker compose up -d), se a porta da URL é a que o Docker publica "
        "(BARNES_PG_PORT no .env; 5433 por padrão) e se usuário e senha estão certos."
    )


def _fetch_applied(conn: psycopg.Connection) -> set[str]:
    """Garante a tabela de controle de migrações e lê o que já foi aplicado."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute("SELECT filename FROM schema_migrations")
        applied = {row[0] for row in cur.fetchall()}
    conn.commit()
    return applied


def apply_migrations(
    conn: psycopg.Connection, migrations_dir: Path = MIGRATIONS_DIR
) -> list[str]:
    """Aplica, em ordem, as migrações de ``migrations_dir`` ainda não registradas.

    Cada arquivo ``.sql`` é executado em uma transação própria; o nome do
    arquivo é gravado em ``schema_migrations`` só se a transação for bem
    sucedida, então rodar de novo é seguro (idempotente).

    Args:
        conn: Conexão psycopg aberta.
        migrations_dir: Diretório com os arquivos de migração. A ordem de
            aplicação segue a ordem alfabética dos nomes — por isso o
            prefixo numérico (``0001_...sql``, ``0002_...sql``).

    Returns:
        Nomes dos arquivos aplicados nesta chamada (vazio se nada pendente).
    """
    applied = _fetch_applied(conn)
    pending = sorted(f for f in migrations_dir.glob("*.sql") if f.name not in applied)

    newly_applied = []
    for migration_file in pending:
        with conn.transaction():
            conn.execute(migration_file.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations (filename) VALUES (%s)",
                (migration_file.name,),
            )
        newly_applied.append(migration_file.name)

    return newly_applied
