"""Erros esperados viram mensagem + código de saída, nunca traceback (CLI).

Sem Postgres: as funções de banco são substituídas via monkeypatch.
"""

from __future__ import annotations

from contextlib import nullcontext

import psycopg
import pytest
from typer.testing import CliRunner

from barnes import cli
from barnes.db.connection import DatabaseConfigError

runner = CliRunner()


def _assert_clean_failure(result, message: str) -> None:
    assert result.exit_code == 1, result.output
    assert message in result.output
    # typer.Exit vira SystemExit; qualquer outra exceção seria um traceback para o operador.
    assert isinstance(result.exception, SystemExit)


@pytest.fixture
def inserted(monkeypatch) -> list:
    calls: list = []
    monkeypatch.setattr(cli, "get_connection", lambda _dsn=None: nullcontext(object()))
    monkeypatch.setattr(cli, "insert_trial", lambda _conn, **kwargs: calls.append(kwargs) or 1)
    return calls


def _load(make_mp4, *args):
    return runner.invoke(cli.app, ["video", "load", str(make_mp4()), "--no-preview", *args])


def test_video_load_with_only_one_id_refuses_instead_of_silently_not_saving(
    inserted, make_mp4
) -> None:
    result = _load(make_mp4, "--experiment-id", "1")
    _assert_clean_failure(result, "--experiment-id e --maze-config-id juntos")
    assert inserted == []


def test_video_load_rejects_unknown_phase_before_touching_the_database(inserted, make_mp4) -> None:
    result = _load(make_mp4, "--experiment-id", "1", "--maze-config-id", "1", "--phase", "treino")
    _assert_clean_failure(result, "--phase deve ser um de")
    assert inserted == []


def test_video_load_without_ids_only_inspects(inserted, make_mp4) -> None:
    result = _load(make_mp4)
    assert result.exit_code == 0, result.output
    assert inserted == []


def test_video_load_duplicate_video_is_explained(monkeypatch, make_mp4) -> None:
    def duplicate(_conn, **_kwargs):
        raise psycopg.errors.UniqueViolation("duplicate key value violates unique constraint")

    monkeypatch.setattr(cli, "get_connection", lambda _dsn=None: nullcontext(object()))
    monkeypatch.setattr(cli, "insert_trial", duplicate)
    result = _load(make_mp4, "--experiment-id", "1", "--maze-config-id", "1")
    _assert_clean_failure(result, "já foi carregado")


def test_video_load_unreadable_file(inserted, tmp_path) -> None:
    result = runner.invoke(cli.app, ["video", "load", str(tmp_path / "nao_existe.mp4")])
    _assert_clean_failure(result, "Arquivo não encontrado")


def test_missing_database_url_is_a_message_not_a_traceback(monkeypatch) -> None:
    def unconfigured(_dsn=None):
        raise DatabaseConfigError("Defina a variável de ambiente BARNES_DATABASE_URL.")

    monkeypatch.setattr(cli, "get_connection", unconfigured)
    for args in (["maze", "show", "1"], ["db", "migrate"], ["trial", "show", "1"]):
        _assert_clean_failure(runner.invoke(cli.app, args), "BARNES_DATABASE_URL")


def test_maze_show_unknown_montagem(monkeypatch) -> None:
    def missing(_conn, maze_config_id):
        raise ValueError(f"maze_config {maze_config_id} não encontrada.")

    monkeypatch.setattr(cli, "get_connection", lambda _dsn=None: nullcontext(object()))
    monkeypatch.setattr(cli, "get_maze_config", missing)
    _assert_clean_failure(runner.invoke(cli.app, ["maze", "show", "99"]), "não encontrada")


def test_maze_create_with_unreadable_reference(tmp_path) -> None:
    result = runner.invoke(
        cli.app,
        [
            "maze", "create",
            "--experiment-id", "1",
            "--name", "x",
            "--reference-frame", str(tmp_path / "nao_existe.mp4"),
            "--arena-diameter-cm", "90",
            "--hole-diameter-cm", "5",
        ],
    )  # fmt: skip
    _assert_clean_failure(result, "Arquivo não encontrado")
