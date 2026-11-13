"""Abertura da conexão: timeout e mensagem de banco indisponível (sem banco real)."""

from __future__ import annotations

import socket
import time

import psycopg
import pytest
from typer.testing import CliRunner

from barnes import cli
from barnes.db import connection
from barnes.db.connection import (
    CONNECT_TIMEOUT_S,
    DatabaseConfigError,
    DatabaseUnavailableError,
    get_connection,
)


def _closed_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_connect_timeout_is_added_when_dsn_has_none(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(connection.psycopg, "connect", lambda dsn, **kw: calls.append(kw))
    get_connection("postgresql://u:p@localhost:5433/barnes")
    assert calls == [{"connect_timeout": CONNECT_TIMEOUT_S}]


def test_connect_timeout_from_dsn_is_respected(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(connection.psycopg, "connect", lambda dsn, **kw: calls.append(kw))
    get_connection("postgresql://u:p@localhost:5433/barnes?connect_timeout=3")
    assert calls == [{}]


def test_unavailable_error_names_host_port_and_database_but_not_the_password(monkeypatch) -> None:
    def refuse(dsn, **kw):
        raise psycopg.OperationalError("connection failed: password=segredo")

    monkeypatch.setattr(connection.psycopg, "connect", refuse)
    with pytest.raises(DatabaseUnavailableError) as info:
        get_connection("postgresql://barnes:segredo@localhost:5432/barnes_demo")
    message = str(info.value)
    assert "localhost:5432" in message
    assert "barnes_demo" in message
    assert "5433 por padrão" in message
    assert "segredo" not in message
    # Continua sendo erro de configuração (CLI) e erro do psycopg (quem trata banco fora do ar).
    assert isinstance(info.value, DatabaseConfigError)
    assert isinstance(info.value, psycopg.OperationalError)


def test_closed_port_fails_instead_of_hanging() -> None:
    dsn = f"postgresql://barnes:segredo@127.0.0.1:{_closed_port()}/barnes?connect_timeout=2"
    started = time.monotonic()
    with pytest.raises(DatabaseUnavailableError):
        get_connection(dsn)
    assert time.monotonic() - started < 15


def test_db_migrate_reports_unreachable_database_without_traceback_or_password() -> None:
    dsn = f"postgresql://barnes:segredo@127.0.0.1:{_closed_port()}/barnes_demo?connect_timeout=2"
    result = CliRunner().invoke(cli.app, ["db", "migrate", "--dsn", dsn])
    assert result.exit_code == 1
    output = result.output
    assert "Não foi possível conectar ao banco 'barnes_demo'" in output
    assert "segredo" not in output
    assert "Traceback" not in output
