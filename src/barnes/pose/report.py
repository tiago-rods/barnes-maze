"""Contagem de quadros anotados por região (US-06 Cenário 2).

Usa o ponto "centro do corpo" **anotado**, não a posição estimada na
amostragem: é a contagem do conjunto que de fato vai treinar o modelo.
"""

from __future__ import annotations

from dataclasses import dataclass

from barnes.geometry.holes import MazeGeometry
from barnes.pose.annotations import AnnotatedFrame
from barnes.pose.regions import Region, RegionParams, classify_region

REFERENCE_POINT = "centro_corpo"


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


def count_by_region(
    frames: list[AnnotatedFrame], geometry: MazeGeometry, params: RegionParams
) -> list[RegionCount]:
    """Conta os quadros anotados por região, pelo centro do corpo anotado.

    Args:
        frames: Conjunto anotado (já validado por `validate_complete`).
        geometry: Geometria da montagem em que os trials foram gravados.
        params: Fronteiras entre as regiões (as mesmas da amostragem).

    Returns:
        Uma contagem por região, na ordem de `Region`.
    """
    counts = dict.fromkeys(Region, 0)
    for frame in frames:
        counts[classify_region(*frame.point(REFERENCE_POINT), geometry, params)] += 1
    total = len(frames)
    return [
        RegionCount(region, counts[region], counts[region] / total if total else 0.0)
        for region in Region
    ]


def empty_regions(counts: list[RegionCount]) -> list[Region]:
    """Regiões sem nenhum quadro anotado — reprovam o Cenário 2."""
    return [count.region for count in counts if count.frames == 0]
