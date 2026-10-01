"""Validação dos parâmetros da geometria paramétrica do Barnes (US-04 RN01, Cenário 3)."""

from __future__ import annotations


class GeometryValidationError(Exception):
    """Parâmetro de geometria inválido; `field` identifica qual (Cenário 3)."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        super().__init__(message)


def validate_parameters(
    *,
    hole_count: int,
    platform_radius_px: float,
    target_hole_number: int,
) -> None:
    """Valida os parâmetros da montagem antes de gerar buracos ou persistir (Cenário 3).

    Args:
        hole_count: Número de buracos, N.
        platform_radius_px: Raio da circunferência dos buracos, em pixels.
        target_hole_number: Índice do buraco-alvo.

    Raises:
        GeometryValidationError: Se N <= 2 (`field="hole_count"`), se o raio
            não for positivo (`field="platform_radius_px"`), ou se o índice
            do alvo estiver fora de 0..N-1 (`field="target_hole_number"`).
    """
    if hole_count <= 2:
        raise GeometryValidationError(
            "hole_count", f"Número de buracos deve ser maior que 2 (recebido {hole_count})."
        )
    if platform_radius_px <= 0:
        raise GeometryValidationError(
            "platform_radius_px",
            f"Raio da plataforma deve ser positivo (recebido {platform_radius_px}).",
        )
    if not (0 <= target_hole_number < hole_count):
        raise GeometryValidationError(
            "target_hole_number",
            f"Índice do alvo deve estar entre 0 e {hole_count - 1} (recebido {target_hole_number}).",
        )
