"""Persistência de trials no banco de dados (US-01 RN05, US-05 RN01)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import psycopg

from barnes.io.trim import TrialInterval, interval_from_seconds
from barnes.io.video import VideoMetadata


def insert_trial(
    conn: psycopg.Connection,
    *,
    experiment_id: int,
    maze_config_id: int,
    video: VideoMetadata,
    phase: str,
    day_number: int,
    trial_number_in_day: int,
    rotation_deg: float | None,
    interval: TrialInterval | None = None,
) -> int:
    """Insere um trial com os metadados de vídeo extraídos pela US-01.

    Não comita a transação — quem chama decide quando persistir (ex.: a
    CLI usa a conexão como context manager, que comita ao sair do bloco
    sem erro).

    Args:
        conn: Conexão psycopg aberta.
        experiment_id: Id do experimento ao qual o trial pertence.
        maze_config_id: Id da configuração de labirinto usada no trial.
        video: Metadados extraídos por `barnes.io.video.load_trial_video`.
        phase: Um de "habituation", "acquisition" ou "probe".
        day_number: Dia do trial dentro do experimento (1-based).
        trial_number_in_day: Ordem do trial dentro do dia (1-based).
        rotation_deg: Rotação da plataforma no trial, em graus (US-05). Sem
            valor padrão de propósito: quem chama decide explicitamente;
            `None` grava NULL ("não registrada"), nunca 0° implícito (RN01).
            Normalizada para 0 <= x < 360 antes de gravar.
        interval: Intervalo útil resolvido por
            `barnes.io.trim.build_trial_interval` (US-03 RN04 — persistido
            para auditoria). Se omitido, `start_time_seconds` e
            `end_time_seconds` ficam nulos e `interval_manually_adjusted`
            fica no padrão (`False`).

    Returns:
        O id do trial recém-criado.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trials (
                experiment_id, maze_config_id, filename, filepath, phase,
                day_number, trial_number_in_day, content_hash, width_px,
                height_px, fps_declared, fps_real, fps_is_variable,
                frame_count, duration_s, rotation_deg, start_time_seconds,
                end_time_seconds, interval_manually_adjusted
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                experiment_id,
                maze_config_id,
                video.path.name,
                str(video.path),
                phase,
                day_number,
                trial_number_in_day,
                video.content_hash,
                video.width,
                video.height,
                video.fps_declared,
                video.fps_real,
                video.fps_is_variable,
                video.frame_count,
                video.duration_s,
                _normalize_rotation(rotation_deg),
                interval.start_s if interval is not None else None,
                interval.end_s if interval is not None else None,
                interval.manually_adjusted if interval is not None else False,
            ),
        )
        return cur.fetchone()[0]


def set_trial_rotation(conn: psycopg.Connection, trial_id: int, rotation_deg: float) -> None:
    """Registra (ou corrige) a rotação da plataforma de um trial existente (US-05 RN01).

    Não comita a transação.

    Args:
        conn: Conexão psycopg aberta.
        trial_id: Id do trial.
        rotation_deg: Rotação em graus; normalizada para 0 <= x < 360.

    Raises:
        ValueError: Se o trial não existir.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE trials SET rotation_deg = %s WHERE id = %s",
            (_normalize_rotation(rotation_deg), trial_id),
        )
        if cur.rowcount == 0:
            raise ValueError(f"Trial {trial_id} não encontrado.")


def get_trial_rotations(
    conn: psycopg.Connection, trial_ids: Iterable[int]
) -> dict[int, float | None]:
    """Lê a rotação registrada de cada trial (US-05).

    Devolve `None` para trial sem rotação (NULL) — a decisão de recusar a
    análise fica com `barnes.geometry.reference_frame.require_rotations`.

    Args:
        conn: Conexão psycopg aberta.
        trial_ids: Ids dos trials a consultar.

    Returns:
        Rotação de cada trial, por id.

    Raises:
        ValueError: Se algum id não existir — trial inexistente não pode
            ser confundido com trial sem rotação.
    """
    ids = list(trial_ids)
    with conn.cursor() as cur:
        cur.execute("SELECT id, rotation_deg FROM trials WHERE id = ANY(%s)", (ids,))
        rotations = dict(cur.fetchall())

    missing = sorted(set(ids) - rotations.keys())
    if missing:
        raise ValueError(f"Trial(s) não encontrado(s): {', '.join(map(str, missing))}.")
    return rotations


@dataclass(frozen=True)
class StoredTrial:
    """O que os estágios do pipeline precisam saber de um trial já carregado.

    Attributes:
        id: Id do trial.
        maze_config_id: Montagem do trial — a única cuja escala e geometria
            valem para ele.
        width_px: Largura do vídeo, em pixels.
        height_px: Altura do vídeo, em pixels.
        interval: Intervalo útil gravado (US-03 RN04), ou `None` se o trial
            foi carregado sem recorte (anterior à US-03).
    """

    id: int
    maze_config_id: int
    width_px: int
    height_px: int
    interval: TrialInterval | None


def get_trial(conn: psycopg.Connection, trial_id: int) -> StoredTrial:
    """Lê um trial com sua montagem e seu intervalo útil (US-03 RN02/RN04).

    Os quadros do intervalo são derivados do `fps_real` gravado pela mesma
    conversão usada ao resolvê-lo (`barnes.io.trim.interval_from_seconds`).

    Raises:
        ValueError: Se o trial não existir.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT maze_config_id, width_px, height_px, fps_real,
                   start_time_seconds, end_time_seconds, interval_manually_adjusted
            FROM trials WHERE id = %s
            """,
            (trial_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"Trial {trial_id} não encontrado.")
    maze_config_id, width, height, fps_real, start_s, end_s, manual = row
    interval = (
        None
        if start_s is None or end_s is None
        else interval_from_seconds(start_s, end_s, fps_real, manually_adjusted=manual)
    )
    return StoredTrial(trial_id, maze_config_id, width, height, interval)


def get_trial_maze_config_id(conn: psycopg.Connection, trial_id: int) -> int:
    """Id da montagem (`maze_configs`) usada por um trial.

    Raises:
        ValueError: Se o trial não existir.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT maze_config_id FROM trials WHERE id = %s", (trial_id,))
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"Trial {trial_id} não encontrado.")
    return row[0]


def _normalize_rotation(rotation_deg: float | None) -> float | None:
    # Respeita o CHECK 0 <= rotation_deg < 360 de trials (migração 0004); um
    # negativo minúsculo (ex.: -1e-20) daria exatamente 360.0 após o módulo.
    if rotation_deg is None:
        return None
    normalized = rotation_deg % 360.0
    return 0.0 if normalized == 360.0 else normalized
