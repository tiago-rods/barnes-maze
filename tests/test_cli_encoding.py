"""Saída da CLI com texto não ASCII quando stdout/stderr não são UTF-8 (ex.: pipe no Windows)."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from barnes import cli

REPO_ROOT = Path(__file__).resolve().parents[1]

# Mesmo caminho do console script `barnes` (`barnes.cli:main`), sem depender do .exe instalado.
_RUN_MAIN = "import sys; sys.argv[0] = 'barnes'; from barnes.cli import main; main()"


def _run_cli_with_cp1252_pipe(*args: str) -> subprocess.CompletedProcess[bytes]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp1252"  # o que o Windows usa quando a saída não é console
    env["PYTHONUTF8"] = "0"
    return subprocess.run(
        [sys.executable, "-c", _RUN_MAIN, *args],
        capture_output=True,  # stdout e stderr em pipe, não console
        env=env,
        cwd=REPO_ROOT,
        timeout=120,
        check=False,
    )


@pytest.mark.parametrize("args", [("--help",), ("scale", "--help")])
def test_help_with_cp1252_piped_stdout_prints_utf8(args):
    result = _run_cli_with_cp1252_pipe(*args)
    stdout = result.stdout.decode("utf-8")
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    assert "px→cm" in stdout
    assert "Calibração" in stdout


def test_console_script_uses_main_not_the_typer_app():
    # Apontar o script direto para `app` pula a reconfiguração e reabre o bug.
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["scripts"]["barnes"] == "barnes.cli:main"


def test_non_utf8_stream_is_reconfigured(monkeypatch):
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stream)
    cli.ensure_utf8_output()
    stream.write("px→cm, ação")
    stream.flush()
    assert stream.encoding == "utf-8"
    assert raw.getvalue().decode("utf-8") == "px→cm, ação"


def test_streams_without_reconfigure_are_left_alone(monkeypatch):
    # CliRunner e afins trocam stdout por objetos sem `reconfigure`; não pode quebrar.
    fake = io.StringIO()
    monkeypatch.setattr(sys, "stdout", fake)
    monkeypatch.setattr(sys, "stderr", None)
    cli.ensure_utf8_output()
    assert sys.stdout is fake
