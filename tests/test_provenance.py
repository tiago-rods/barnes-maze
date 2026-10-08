"""Captura de commit, estado sujo e limiares (US-27 RN01/RN05, Cenário 4).

O commit e o estado sujo vêm de `git_revision_record` (US-07/08), a única
captura do sistema; aqui se testa o que a US-27 depende dela.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from barnes.pose.dataset import git_revision_record
from barnes.provenance import GitState, thresholds_snapshot

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="Requer git instalado.")


def git_state(repo: Path) -> GitState:
    return GitState.from_record(git_revision_record(repo))


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "teste@example.com")
    _git(tmp_path, "config", "user.name", "Teste")
    _git(tmp_path, "config", "core.autocrlf", "false")
    (tmp_path / ".gitignore").write_text("ignorado.txt\n", encoding="utf-8")
    (tmp_path / "codigo.py").write_text("x = 1\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "inicial")
    return tmp_path


def test_clean_repository_records_commit_and_is_reproducible(repo):
    state = git_state(repo)
    assert state.commit is not None and len(state.commit) == 40
    assert state.dirty is False
    assert state.reproducible


def test_uncommitted_change_marks_dirty(repo):
    (repo / "codigo.py").write_text("x = 2\n", encoding="utf-8")
    state = git_state(repo)
    assert state.dirty is True
    assert not state.reproducible


def test_untracked_file_marks_dirty(repo):
    (repo / "novo.py").write_text("y = 1\n", encoding="utf-8")
    assert git_state(repo).dirty is True


def test_ignored_file_does_not_mark_dirty(repo):
    (repo / "ignorado.txt").write_text("dado local\n", encoding="utf-8")
    assert git_state(repo).dirty is False


def test_outside_repository_is_unknown_never_clean(tmp_path):
    if not _no_parent_repo(tmp_path):
        pytest.skip("tmp_path está dentro de um repositório git.")
    state = git_state(tmp_path)
    assert state.commit is None
    assert state.dirty is None
    assert not state.reproducible


def _no_parent_repo(path: Path) -> bool:
    return (
        subprocess.run(
            ["git", "rev-parse", "--git-dir"], cwd=path, capture_output=True, check=False
        ).returncode
        != 0
    )


def test_thresholds_snapshot_keeps_nulls_and_hash(tmp_path):
    config = tmp_path / "default.yaml"
    config.write_text("encontrar:\n  distancia_cm: null\n", encoding="utf-8")
    snapshot = thresholds_snapshot(config)
    assert snapshot.values == {"encontrar": {"distancia_cm": None}}
    assert len(snapshot.sha256) == 64

    config.write_text("encontrar:\n  distancia_cm: 5\n", encoding="utf-8")
    assert thresholds_snapshot(config).sha256 != snapshot.sha256


def test_thresholds_snapshot_rejects_non_mapping(tmp_path):
    config = tmp_path / "default.yaml"
    config.write_text("- lista\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mapeamento"):
        thresholds_snapshot(config)


def test_project_thresholds_file_is_readable():
    snapshot = thresholds_snapshot()
    assert "encontrar" in snapshot.values
