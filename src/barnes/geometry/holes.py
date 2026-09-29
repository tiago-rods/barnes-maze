"""Geometria paramétrica do labirinto de Barnes (US-04).

Convenção fixada por este módulo (sem precedente anterior no repositório):
coordenadas em pixels de imagem OpenCV (origem no canto superior-esquerdo,
y crescendo para baixo); ângulo 0° aponta para +x, crescente no sentido
horário na tela (decorre naturalmente de usar +sin com y para baixo).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import shapely

from barnes.geometry.validation import validate_parameters


@dataclass(frozen=True)
class Hole:
    """Um buraco da montagem, posicionado sobre a circunferência da plataforma.

    Attributes:
        hole_number: Índice do buraco na montagem, 0..N-1 (RN02/RN03).
        angle_deg: Ângulo do buraco, normalizado para 0 <= x < 360 (RN02;
            respeita o CHECK de `holes.angle_deg` no banco).
        x_px: Coordenada x do centro do buraco, em pixels.
        y_px: Coordenada y do centro do buraco, em pixels.
        radius_px: Raio do buraco, em pixels (RN06).
        is_target: True se este é o buraco-alvo da montagem (RN03).
    """

    hole_number: int
    angle_deg: float
    x_px: float
    y_px: float
    radius_px: float
    is_target: bool

    def proximity_zone(self, margin_px: float = 0.0) -> shapely.Polygon:
        """Zona de proximidade do buraco, para os eventos do Épico D (RN06).

        Args:
            margin_px: Margem somada ao raio físico do buraco, em pixels
                (0 = a zona coincide com o círculo do buraco).

        Returns:
            Um polígono Shapely representando a zona.
        """
        return shapely.Point(self.x_px, self.y_px).buffer(self.radius_px + margin_px)


@dataclass(frozen=True)
class MazeGeometry:
    """Geometria completa de uma montagem do labirinto de Barnes (RN01-RN03).

    Attributes:
        center_x_px: Coordenada x do centro da plataforma, em pixels.
        center_y_px: Coordenada y do centro da plataforma, em pixels.
        platform_radius_px: Raio da circunferência onde os buracos são
            distribuídos, em pixels.
        holes: Os N buracos gerados, ordenados por hole_number (0..N-1).
    """

    center_x_px: float
    center_y_px: float
    platform_radius_px: float
    holes: tuple[Hole, ...]

    @property
    def hole_count(self) -> int:
        """Número de buracos da montagem (N)."""
        return len(self.holes)

    @property
    def target_hole(self) -> Hole:
        """O buraco marcado como alvo (RN03).

        Raises:
            ValueError: Se nenhum buraco estiver marcado como alvo — não
                deveria acontecer em uma montagem que passou por
                `validate_parameters`, mas protege contra construção manual.
        """
        for hole in self.holes:
            if hole.is_target:
                return hole
        raise ValueError("Nenhum buraco desta montagem está marcado como alvo.")


def generate_holes(
    *,
    center_x_px: float,
    center_y_px: float,
    platform_radius_px: float,
    hole_count: int,
    start_angle_deg: float,
    target_hole_number: int,
    hole_radius_px: float,
) -> MazeGeometry:
    """Gera os N buracos igualmente espaçados sobre a circunferência (RN01/RN02).

    Args:
        center_x_px: Coordenada x do centro da plataforma, em pixels.
        center_y_px: Coordenada y do centro da plataforma, em pixels.
        platform_radius_px: Raio da circunferência dos buracos, em pixels.
        hole_count: Número de buracos, N (RN01).
        start_angle_deg: Ângulo do buraco de índice 0, em graus. Pode vir
            fora de [0, 360) — é normalizado internamente.
        target_hole_number: Índice (0..N-1) do buraco-alvo (RN03).
        hole_radius_px: Raio de cada buraco, em pixels (RN06); igual para
            todos os buracos desta montagem.

    Returns:
        A geometria completa, com os buracos ordenados por hole_number.

    Raises:
        GeometryValidationError: Se algum parâmetro for inválido (Cenário 3)
            — ver `barnes.geometry.validation.validate_parameters`.
    """
    validate_parameters(
        hole_count=hole_count,
        platform_radius_px=platform_radius_px,
        target_hole_number=target_hole_number,
    )

    step_deg = 360.0 / hole_count
    holes = tuple(
        _build_hole(
            hole_number=k,
            angle_deg=(start_angle_deg + k * step_deg) % 360.0,
            center_x_px=center_x_px,
            center_y_px=center_y_px,
            platform_radius_px=platform_radius_px,
            radius_px=hole_radius_px,
            is_target=(k == target_hole_number),
        )
        for k in range(hole_count)
    )
    return MazeGeometry(
        center_x_px=center_x_px,
        center_y_px=center_y_px,
        platform_radius_px=platform_radius_px,
        holes=holes,
    )


def _build_hole(
    *,
    hole_number: int,
    angle_deg: float,
    center_x_px: float,
    center_y_px: float,
    platform_radius_px: float,
    radius_px: float,
    is_target: bool,
) -> Hole:
    angle_rad = math.radians(angle_deg)
    return Hole(
        hole_number=hole_number,
        angle_deg=angle_deg,
        x_px=center_x_px + platform_radius_px * math.cos(angle_rad),
        y_px=center_y_px + platform_radius_px * math.sin(angle_rad),
        radius_px=radius_px,
        is_target=is_target,
    )
