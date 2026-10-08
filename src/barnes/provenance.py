"""Proveniência de execuções: commit do código, estado sujo e limiares vigentes (US-27).

Ponto único de captura, usado por todo estágio que registra uma linha em
`execucao` (pose, métricas e os que vierem). Um resultado só é reproduzível
se o commit registrado for exatamente o código executado — por isso o estado
"sujo" (alterações não commitadas, inclusive arquivos novos não rastreados) é
registrado junto (RN05), e um repositório sem git devolve `None`, nunca
"limpo" por omissão.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_THRESHOLDS_PATH = Path("configs/default.yaml")


@dataclass(frozen=True)
class GitState:
    """Revisão do código no momento da execução.

    Attributes:
        commit: Hash completo do `HEAD`, ou `None` se não houver git/repositório.
        dirty: True se houver alterações não commitadas (incluindo arquivos não
            rastreados e não ignorados); `None` se não foi possível verificar.
    """

    commit: str | None
    dirty: bool | None

    @property
    def reproducible(self) -> bool:
        """True só quando o commit é conhecido e o repositório estava limpo."""
        return self.commit is not None and self.dirty is False


def git_state(repo: Path = PACKAGE_DIR) -> GitState:
    """Lê o commit e o estado sujo do repositório que contém `repo`.

    Args:
        repo: Qualquer diretório dentro do repositório (padrão: o do pacote).

    Returns:
        O estado lido; campos `None` quando git não está disponível ou
        `repo` não pertence a um repositório.
    """
    try:
        commit = _git(repo, "rev-parse", "HEAD")
        dirty = bool(_git(repo, "status", "--porcelain"))
    except (OSError, subprocess.SubprocessError):
        return GitState(commit=None, dirty=None)
    return GitState(commit=commit, dirty=dirty)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True, timeout=10
    ).stdout.strip()


def file_sha256(path: Path) -> str:
    """SHA-256 hexadecimal do conteúdo de um arquivo."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_record(package: Path = PACKAGE_DIR) -> dict[str, Any]:
    """Identifica o código executado, inclusive alterações ainda sem commit.

    Returns:
        `git_commit`, `git_dirty` e o SHA-256 de cada `.py` do pacote — este
        último permite reconhecer o código exato mesmo numa execução suja.
    """
    state = git_state(package)
    return {
        "python_files_sha256": {
            path.relative_to(package).as_posix(): file_sha256(path)
            for path in sorted(package.rglob("*.py"))
        },
        "git_commit": state.commit,
        "git_dirty": state.dirty,
    }


@dataclass(frozen=True)
class ThresholdsSnapshot:
    """Limiares operacionais vigentes numa execução (RN01).

    Attributes:
        values: Conteúdo de `configs/default.yaml`, como dicionário — inclusive
            os `null` ainda não definidos em G3, que também são informação.
        sha256: Hash dos bytes do arquivo, para comparar execuções sem
            depender da formatação do YAML.
        path: Caminho lido.
    """

    values: dict[str, Any]
    sha256: str
    path: str


def thresholds_snapshot(path: Path = DEFAULT_THRESHOLDS_PATH) -> ThresholdsSnapshot:
    """Congela os limiares lidos para o registro da execução.

    Raises:
        OSError: Se o arquivo não puder ser lido.
        ValueError: Se o YAML não for um mapeamento.
    """
    raw = Path(path).read_bytes()
    values = yaml.safe_load(raw)
    if not isinstance(values, dict):
        raise ValueError(f"Limiares inválidos em {path}: esperado um mapeamento YAML.")  # noqa: TRY004
    return ThresholdsSnapshot(
        values=values, sha256=hashlib.sha256(raw).hexdigest(), path=Path(path).as_posix()
    )
