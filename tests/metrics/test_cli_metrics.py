"""`metrics distance-validate` sem referência manual (US-18 SCRUM-225): não precisa de banco."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from barnes import cli

runner = CliRunner()


def test_without_manual_reference_the_round_is_recorded_as_blocked(tmp_path):
    out = tmp_path / "rodadas"
    result = runner.invoke(cli.app, ["metrics", "distance-validate", "--saida", str(out)])
    assert result.exit_code == 2
    assert "Bloqueado" in result.output
    (record_path,) = out.glob("*/correlacao.json")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["status"] == "bloqueado"
    assert record["limiar"] == 0.95
    assert (record_path.parent / "correlacao.md").is_file()


def test_missing_manual_file_is_also_blocked_not_a_crash(tmp_path):
    result = runner.invoke(
        cli.app,
        [
            "metrics", "distance-validate",
            "--manual", str(tmp_path / "ainda-nao-entregue.csv"),
            "--saida", str(tmp_path / "rodadas"),
        ],
    )
    assert result.exit_code == 2
