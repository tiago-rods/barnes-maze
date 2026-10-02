"""Divisão treino/validação/teste por trial e verificação de vazamento (US-06 RN03).

Quadros do mesmo trial são quase idênticos entre si: se um trial tiver
quadros em treino e em teste, o modelo é avaliado em algo que praticamente já
viu e a métrica de teste fica inflada. Por isso a unidade da divisão é o
trial, nunca o quadro — e a verificação de vazamento é automática.
"""

from __future__ import annotations

import csv
import math
import random
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from barnes.pose.annotations import AnnotatedFrame
from barnes.pose.protocol import SplitProportions

SETS = ("treino", "validacao", "teste")
SPLIT_CSV = "divisao.csv"


class SplitError(ValueError):
    """Divisão impossível com os trials e proporções informados."""


class SplitLeakageError(ValueError):
    """Um ou mais trials aparecem em mais de um conjunto (Cenário 3).

    Attributes:
        leaks: Para cada trial com vazamento, os conjuntos em que ele aparece.
    """

    def __init__(self, leaks: dict[str, set[str]]) -> None:
        self.leaks = leaks
        detail = "; ".join(
            f"trial {trial} em {', '.join(sorted(sets))}" for trial, sets in sorted(leaks.items())
        )
        super().__init__(f"Vazamento entre conjuntos — refaça a divisão: {detail}.")


@dataclass(frozen=True)
class ManifestRow:
    """Uma linha do manifesto da divisão: a qual conjunto pertence cada quadro."""

    trial: str
    frame_index: int
    subset: str


def _counts(n: int, proportions: SplitProportions) -> dict[str, int]:
    """Quantos trials vão para cada conjunto (maiores restos, mínimo 1 por conjunto usado)."""
    weights = {
        "treino": proportions.treino,
        "validacao": proportions.validacao,
        "teste": proportions.teste,
    }
    if any(w < 0 for w in weights.values()) or not math.isclose(sum(weights.values()), 1.0):
        raise SplitError("As proporções da divisão devem ser não negativas e somar 1.")
    used = [name for name in SETS if weights[name] > 0]
    if n < len(used):
        raise SplitError(
            f"São necessários ao menos {len(used)} trials para dividir em "
            f"{', '.join(used)} sem repetir trial (há {n})."
        )

    exact = {name: n * weights[name] for name in SETS}
    counts = {name: math.floor(exact[name]) for name in SETS}
    by_remainder = sorted(SETS, key=lambda name: exact[name] - counts[name], reverse=True)
    for name in by_remainder[: n - sum(counts.values())]:
        counts[name] += 1

    # Todo conjunto com proporção > 0 recebe ao menos um trial, tirado do maior.
    for name in used:
        if counts[name] == 0:
            donor = max(SETS, key=lambda other: counts[other])
            counts[donor] -= 1
            counts[name] += 1
    return counts


def split_by_trial(
    trials: Iterable[str], proportions: SplitProportions, seed: int
) -> dict[str, str]:
    """Sorteia, de forma reprodutível, o conjunto de cada trial (RN03).

    Args:
        trials: Chaves dos trials anotados (repetições são ignoradas).
        proportions: Proporção de trials em treino/validação/teste.
        seed: Semente do sorteio — mesma semente, mesma divisão.

    Returns:
        `{trial: conjunto}`, com conjunto em `SETS`.

    Raises:
        SplitError: Se as proporções forem inválidas ou houver menos trials
            do que conjuntos a preencher.
    """
    unique = sorted(set(trials))
    counts = _counts(len(unique), proportions)
    random.Random(seed).shuffle(unique)

    assignment: dict[str, str] = {}
    position = 0
    for name in SETS:
        for trial in unique[position : position + counts[name]]:
            assignment[trial] = name
        position += counts[name]
    return assignment


def build_manifest(frames: list[AnnotatedFrame], assignment: dict[str, str]) -> list[ManifestRow]:
    """Atribui cada quadro anotado ao conjunto do seu trial."""
    return [
        ManifestRow(frame.trial, frame.frame_index, assignment[frame.trial])
        for frame in sorted(frames, key=lambda f: (f.trial, f.frame_index))
    ]


def write_manifest(rows: list[ManifestRow], path: str | Path) -> Path:
    """Grava o manifesto da divisão (`trial, quadro, conjunto`)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["trial", "quadro", "conjunto"])
        for row in rows:
            writer.writerow([row.trial, row.frame_index, row.subset])
    return path


def read_manifest(path: str | Path) -> list[ManifestRow]:
    """Lê o manifesto da divisão.

    Raises:
        ValueError: Se faltar coluna, um valor for inválido ou o conjunto
            não for um de `SETS`.
    """
    path = Path(path)
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not {"trial", "quadro", "conjunto"}.issubset(reader.fieldnames or []):
            raise ValueError(f"{path.name} exige as colunas trial,quadro,conjunto.")
        rows = []
        for row in reader:
            if row["conjunto"] not in SETS:
                raise ValueError(
                    f"Conjunto inválido '{row['conjunto']}' na linha {reader.line_num} "
                    f"de {path.name} (use {', '.join(SETS)})."
                )
            try:
                rows.append(ManifestRow(row["trial"], int(row["quadro"]), row["conjunto"]))
            except ValueError as exc:
                raise ValueError(
                    f"Quadro inválido na linha {reader.line_num} de {path.name}."
                ) from exc
    return rows


def check_no_leakage(rows: Iterable[ManifestRow]) -> None:
    """Falha se algum trial tiver quadros em mais de um conjunto (Cenário 3).

    Raises:
        SplitLeakageError: Apontando cada trial duplicado e seus conjuntos.
    """
    sets_by_trial: dict[str, set[str]] = {}
    for row in rows:
        sets_by_trial.setdefault(row.trial, set()).add(row.subset)
    leaks = {trial: sets for trial, sets in sets_by_trial.items() if len(sets) > 1}
    if leaks:
        raise SplitLeakageError(leaks)


def summarize(rows: Iterable[ManifestRow]) -> dict[str, tuple[int, int]]:
    """`{conjunto: (nº de trials, nº de quadros)}`, para o protocolo."""
    trials: dict[str, set[str]] = {name: set() for name in SETS}
    frames = dict.fromkeys(SETS, 0)
    for row in rows:
        trials[row.subset].add(row.trial)
        frames[row.subset] += 1
    return {name: (len(trials[name]), frames[name]) for name in SETS}
