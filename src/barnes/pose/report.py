"""Contagem de quadros anotados por região (US-06 Cenário 2).

Usa o ponto "centro do corpo" **anotado**, não a posição estimada na
amostragem: é a contagem do conjunto que de fato vai treinar o modelo.

Cada trial é classificado com a geometria da **sua** montagem: trials de dias
diferentes podem ter a câmera deslocada (preocupação registrada em US-05), e
classificar todos com uma montagem só erraria a região sem nenhum aviso.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from barnes.geometry.holes import MazeGeometry
from barnes.pose.annotations import AnnotatedFrame
from barnes.pose.regions import Region, RegionParams, classify_region

REFERENCE_POINT = "centro_corpo"


class MazeConfigResolutionError(ValueError):
    """Não dá para saber, sem ambiguidade, a montagem de algum trial anotado."""


@dataclass(frozen=True)
class RegionCount:
    """Quadros anotados numa região.

    Attributes:
        region: A região.
        frames: Número de quadros anotados nela.
        proportion: Fração do total de quadros anotados (0..1).
    """

    region: Region
    frames: int
    proportion: float


def resolve_maze_configs(
    trials: Iterable[str], recorded: Mapping[str, int | None], override: int | None
) -> dict[str, int]:
    """Decide a montagem de cada trial para a contagem por região.

    Vale a montagem registrada pela amostragem (`amostragem.csv`). `override`
    (o `--maze-config-id` da CLI) só preenche trials sem registro — ele nunca
    substitui em silêncio uma montagem registrada diferente.

    Args:
        trials: Chaves dos trials anotados.
        recorded: Montagem registrada por trial (`None` = sem registro).
        override: Montagem informada pelo operador, ou `None`.

    Returns:
        `{trial: maze_config_id}` para todos os trials.

    Raises:
        MazeConfigResolutionError: Se `override` contradisser o registro de
            algum trial, ou se algum trial ficar sem montagem.
    """
    resolved: dict[str, int] = {}
    conflicts, unknown = [], []
    for trial in sorted(set(trials)):
        saved = recorded.get(trial)
        if saved is not None and override is not None and saved != override:
            conflicts.append(f"{trial} (amostrado com a montagem {saved})")
        elif saved is not None:
            resolved[trial] = saved
        elif override is not None:
            resolved[trial] = override
        else:
            unknown.append(trial)
    if conflicts:
        raise MazeConfigResolutionError(
            f"--maze-config-id {override} contradiz a montagem registrada na amostragem de: "
            f"{', '.join(conflicts)}. Omita --maze-config-id para usar a de cada trial."
        )
    if unknown:
        raise MazeConfigResolutionError(
            f"Montagem desconhecida para o(s) trial(s) {', '.join(unknown)}: sem "
            "<trial>/amostragem.csv com maze_config_id. Refaça `barnes pose sample` "
            "ou informe --maze-config-id."
        )
    return resolved


def count_by_region(
    frames: list[AnnotatedFrame],
    geometries: Mapping[str, MazeGeometry],
    params: RegionParams,
) -> list[RegionCount]:
    """Conta os quadros anotados por região, pelo centro do corpo anotado.

    Args:
        frames: Conjunto anotado (já validado por `validate_complete`).
        geometries: Geometria da montagem de cada trial, por chave de trial.
        params: Fronteiras entre as regiões (as mesmas da amostragem).

    Returns:
        Uma contagem por região, na ordem de `Region`.

    Raises:
        KeyError: Se algum trial anotado não tiver geometria.
    """
    counts = dict.fromkeys(Region, 0)
    for frame in frames:
        geometry = geometries[frame.trial]
        counts[classify_region(*frame.point(REFERENCE_POINT), geometry, params)] += 1
    total = len(frames)
    return [
        RegionCount(region, counts[region], counts[region] / total if total else 0.0)
        for region in Region
    ]


def empty_regions(counts: list[RegionCount]) -> list[Region]:
    """Regiões sem nenhum quadro anotado — reprovam o Cenário 2."""
    return [count.region for count in counts if count.frames == 0]
