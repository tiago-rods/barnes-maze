"""Persistência de trials no banco de dados (US-01 RN05)."""

from __future__ import annotations

import psycopg

from barnes.io.trim import TrialInterval
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
                frame_count, duration_s, start_time_seconds, end_time_seconds,
                interval_manually_adjusted
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                interval.start_s if interval is not None else None,
                interval.end_s if interval is not None else None,
                interval.manually_adjusted if interval is not None else False,
            ),
        )
        return cur.fetchone()[0]
