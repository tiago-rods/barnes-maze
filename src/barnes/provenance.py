"""Proveniência de execuções: estado do código e limiares vigentes (US-27).

A captura do commit e do estado sujo é a de `barnes.pose.dataset.git_revision_record`
(US-07/08) — única no sistema; aqui só fica o tipo `GitState`, que o registro em
`execucao` consome, e o snapshot dos limiares. Um resultado só é reproduzível se o
commit registrado for exatamente o código executado — por isso o estado "sujo"
(alterações não commitadas, inclusive arquivos novos não rastreados) é registrado
junto (RN05), e um repositório sem git dá `None`, nunca "limpo" por omissão.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# Diretório do pacote `barnes` — dentro do repositório cujo commit é registrado.
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

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> GitState:
        """Constrói a partir do dicionário de `git_revision_record` (`git_commit`/`git_dirty`)."""
        return cls(commit=record.get("git_commit"), dirty=record.get("git_dirty"))

    @property
    def reproducible(self) -> bool:
        """True só quando o commit é conhecido e o repositório estava limpo."""
        return self.commit is not None and self.dirty is False


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
