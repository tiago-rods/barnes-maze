"""Persistência da geometria do labirinto no banco de dados (US-04 RN04/RN05)."""

from __future__ import annotations

import psycopg

from barnes.geometry.holes import Hole, MazeGeometry


def insert_maze_config(
    conn: psycopg.Connection,
    *,
    experiment_id: int,
    name: str,
    arena_diameter_cm: float,
    hole_diameter_cm: float,
    geometry: MazeGeometry,
) -> int:
    """Insere a configuração de labirinto e seus buracos (RN01-RN03).

    Não comita a transação — quem chama decide quando persistir.

    Args:
        conn: Conexão psycopg aberta.
        experiment_id: Id do experimento ao qual esta montagem pertence.
        name: Nome/rótulo da montagem (ex. "setup padrão").
        arena_diameter_cm: Diâmetro da arena, em cm (independente de px).
        hole_diameter_cm: Diâmetro de cada buraco, em cm.
        geometry: Geometria já gerada e validada por
            `barnes.geometry.holes.generate_holes`.

    Returns:
        O id da `maze_configs` recém-criada (buracos já inseridos).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO maze_configs (
                experiment_id, name, arena_diameter_cm, hole_count,
                hole_diameter_cm, center_x_px, center_y_px, platform_radius_px
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                experiment_id,
                name,
                arena_diameter_cm,
                geometry.hole_count,
                hole_diameter_cm,
                geometry.center_x_px,
                geometry.center_y_px,
                geometry.platform_radius_px,
            ),
        )
        maze_config_id = cur.fetchone()[0]

    insert_holes(conn, maze_config_id=maze_config_id, holes=geometry.holes)
    return maze_config_id


def insert_holes(
    conn: psycopg.Connection,
    *,
    maze_config_id: int,
    holes: tuple[Hole, ...] | list[Hole],
) -> None:
    """Insere os buracos de uma montagem (RN02/RN03/RN06).

    Não comita a transação.

    Args:
        conn: Conexão psycopg aberta.
        maze_config_id: Id da `maze_configs` à qual estes buracos pertencem.
        holes: Buracos a inserir, com hole_number já definitivo (0..N-1).
    """
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO holes (
                maze_config_id, hole_number, angle_deg, x_px, y_px, radius_px, is_target
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    maze_config_id,
                    hole.hole_number,
                    hole.angle_deg,
                    hole.x_px,
                    hole.y_px,
                    hole.radius_px,
                    hole.is_target,
                )
                for hole in holes
            ],
        )


def get_maze_config(conn: psycopg.Connection, maze_config_id: int) -> MazeGeometry:
    """Lê uma montagem do banco e reconstrói a geometria (RN05, Cenário 2).

    Reaplica geometria e alvo sem qualquer interação nova. A escala px->cm
    (US-02) mora nos mesmos registros de `maze_configs` (coluna
    `px_per_10cm`) e pode ser lida separadamente por quem precisar dela —
    esta função retorna só a geometria, para não acoplar `geometry` à
    leitura de calibração (US-02).

    Todas as coordenadas e raios em pixel são `DOUBLE PRECISION` (desde a
    migração 0005; antes, centro e buracos eram `INTEGER` e voltavam
    arredondados), então a geometria lida é a mesma gerada por
    `generate_holes`.

    Args:
        conn: Conexão psycopg aberta.
        maze_config_id: Id da `maze_configs` a carregar.

    Returns:
        A geometria reconstruída, com os buracos ordenados por hole_number.

    Raises:
        ValueError: Se a montagem não existir, não tiver buracos
            cadastrados, ou não tiver geometria definida (centro/raio nulos).
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT center_x_px, center_y_px, platform_radius_px FROM maze_configs WHERE id = %s",
            (maze_config_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"maze_config {maze_config_id} não encontrada.")
        center_x_px, center_y_px, platform_radius_px = row
        if center_x_px is None or center_y_px is None or platform_radius_px is None:
            raise ValueError(f"maze_config {maze_config_id} não tem geometria definida.")

        cur.execute(
            """
            SELECT hole_number, angle_deg, x_px, y_px, radius_px, is_target
            FROM holes WHERE maze_config_id = %s ORDER BY hole_number
            """,
            (maze_config_id,),
        )
        rows = cur.fetchall()

    if not rows:
        raise ValueError(f"maze_config {maze_config_id} não tem buracos cadastrados.")

    holes = tuple(
        Hole(
            hole_number=r[0], angle_deg=r[1], x_px=r[2], y_px=r[3], radius_px=r[4], is_target=r[5]
        )
        for r in rows
    )
    return MazeGeometry(
        center_x_px=center_x_px,
        center_y_px=center_y_px,
        platform_radius_px=platform_radius_px,
        holes=holes,
    )
