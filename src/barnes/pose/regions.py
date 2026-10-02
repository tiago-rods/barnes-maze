"""Classificação da posição do animal em região da plataforma (US-06 RN02).

As três regiões do protocolo de anotação — centro, borda e proximidade de
buraco — também são as regiões em que o erro do modelo de pose é reportado
separadamente (US-08), por isso a classificação mora num módulo próprio.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

import shapely

from barnes.geometry.holes import MazeGeometry


class Region(Enum):
    """Região da plataforma, com os nomes usados em CSV e em `configs/default.yaml`."""

    CENTRO = "centro"
    BORDA = "borda"
    BURACO = "buraco"


@dataclass(frozen=True)
class RegionParams:
    """Fronteiras entre as regiões (seção `anotacao.regioes` da configuração).

    Attributes:
        center_radius_frac: Até esta fração de `platform_radius_px` (raio da
            circunferência dos buracos) a posição conta como "centro".
        hole_margin_radii: Margem somada ao raio físico do buraco, em
            múltiplos desse raio, para contar como "proximidade de buraco".
            Expressa em raios, não em pixels, para não depender da resolução.
    """

    center_radius_frac: float
    hole_margin_radii: float

    def __post_init__(self) -> None:
        if not 0 < self.center_radius_frac < 1:
            raise ValueError("centro_raio_frac deve estar entre 0 e 1 (exclusivo).")
        if self.hole_margin_radii < 0:
            raise ValueError("buraco_margem_raios não pode ser negativo.")


def classify_region(
    x_px: float, y_px: float, geometry: MazeGeometry, params: RegionParams
) -> Region:
    """Classifica um ponto da imagem em uma das três regiões.

    A proximidade de buraco tem prioridade: é onde a perda de pose é mais
    provável e mais cara, e um ponto junto a um buraco também está, por
    construção, perto da borda. Tudo que não é centro nem buraco é borda —
    inclusive pontos além da circunferência dos buracos.

    Args:
        x_px: Coordenada x do ponto, em pixels.
        y_px: Coordenada y do ponto, em pixels.
        geometry: Geometria da montagem (US-04).
        params: Fronteiras entre as regiões.

    Returns:
        A região do ponto.
    """
    point = shapely.Point(x_px, y_px)
    for hole in geometry.holes:
        if hole.proximity_zone(hole.radius_px * params.hole_margin_radii).covers(point):
            return Region.BURACO

    distance = math.hypot(x_px - geometry.center_x_px, y_px - geometry.center_y_px)
    if distance <= geometry.platform_radius_px * params.center_radius_frac:
        return Region.CENTRO
    return Region.BORDA
