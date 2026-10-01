"""Seed da montagem real do LNBio (US-04 DoD).

ATENÇÃO: os valores abaixo são PLACEHOLDER, pendentes da pergunta B2 do
questionário do laboratório (número de buracos e diâmetro da plataforma).
Não usar em produção antes de B2 ser respondida. Isto reproduz a mesma
pendência que `configs/montagens/lnbio_barnes.yaml` documentava (todos os
campos vinham `null`) — não é uma regressão, apenas troca o formato de YAML
para script versionado sobre o Postgres (ver docs/revisao-cards.md).
"""

from __future__ import annotations

import psycopg

from barnes.db.connection import get_connection
from barnes.db.maze_configs import insert_maze_config
from barnes.geometry.holes import generate_holes

EXPERIMENT_ID = None  # TODO(B2): id do experimento LNBio real no banco
CENTER_X_PX = None
CENTER_Y_PX = None
PLATFORM_RADIUS_PX = None
HOLE_COUNT = None  # TODO(B2)
START_ANGLE_DEG = None
TARGET_HOLE_NUMBER = None
HOLE_RADIUS_PX = None
ARENA_DIAMETER_CM = None  # TODO(B2)
HOLE_DIAMETER_CM = None  # TODO(B2)


def run(conn: psycopg.Connection) -> int:
    """Executa o seed; levanta erro claro se os placeholders não tiverem sido preenchidos.

    Args:
        conn: Conexão psycopg aberta.

    Returns:
        O id da `maze_configs` recém-criada.

    Raises:
        RuntimeError: Se os valores pendentes de B2 ainda não foram
            preenchidos neste arquivo.
    """
    if HOLE_COUNT is None:
        raise RuntimeError(
            "Seed do LNBio pendente: preencha os valores em database/seeds/lnbio_barnes.py "
            "após a pergunta B2 (número de buracos e diâmetro da plataforma) ser respondida."
        )
    geometry = generate_holes(
        center_x_px=CENTER_X_PX,
        center_y_px=CENTER_Y_PX,
        platform_radius_px=PLATFORM_RADIUS_PX,
        hole_count=HOLE_COUNT,
        start_angle_deg=START_ANGLE_DEG,
        target_hole_number=TARGET_HOLE_NUMBER,
        hole_radius_px=HOLE_RADIUS_PX,
    )
    return insert_maze_config(
        conn,
        experiment_id=EXPERIMENT_ID,
        name="lnbio_barnes",
        arena_diameter_cm=ARENA_DIAMETER_CM,
        hole_diameter_cm=HOLE_DIAMETER_CM,
        geometry=geometry,
    )


if __name__ == "__main__":
    # Rodar como `uv run python -m database.seeds.lnbio_barnes` a partir da
    # raiz do repositório (não é um comando de `barnes`, pois este script
    # vive fora do pacote instalado em src/barnes/).
    with get_connection() as connection:
        new_id = run(connection)
    print(f"Montagem lnbio_barnes #{new_id} salva no banco.")
