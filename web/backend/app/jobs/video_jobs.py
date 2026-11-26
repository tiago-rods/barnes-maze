"""Job RQ: carrega um vídeo e registra o trial (US-01/03/05).

Mesma sequência que `cli.py`'s `video load` já executa — `load_trial_video`
-> `build_trial_interval` -> `insert_trial`, com as mesmas traduções de
erro — só que dentro do processo do worker RQ em vez do processo da CLI.
"""

from __future__ import annotations

import psycopg
from rq import get_current_job

from barnes.db.connection import get_connection
from barnes.db.jobs import mark_failed, mark_finished, mark_started
from barnes.db.trials import insert_trial
from barnes.io.trim import TrialIntervalError, build_trial_interval
from barnes.io.video import VideoLoadError, load_trial_video


def run_load_trial(
    *,
    path: str,
    experiment_id: int,
    maze_config_id: int,
    phase: str,
    day_number: int,
    trial_number_in_day: int,
    rotation_deg: float = 0.0,
    start_s: float | None = None,
    end_s: float | None = None,
    dsn: str | None = None,
) -> dict:
    job = get_current_job()
    with get_connection(dsn) as conn:
        mark_started(conn, job.id)

    try:
        video = load_trial_video(path)
        interval = build_trial_interval(video, start_s=start_s, end_s=end_s)
        with get_connection(dsn) as conn:
            trial_id = insert_trial(
                conn,
                experiment_id=experiment_id,
                maze_config_id=maze_config_id,
                video=video,
                phase=phase,
                day_number=day_number,
                trial_number_in_day=trial_number_in_day,
                rotation_deg=rotation_deg,
                interval=interval,
            )
    except VideoLoadError as exc:
        _fail(dsn, job.id, str(exc))
        raise
    except TrialIntervalError as exc:
        _fail(dsn, job.id, f"Erro no intervalo útil: {exc}")
        raise
    except psycopg.errors.UniqueViolation:
        _fail(
            dsn,
            job.id,
            "Este vídeo já foi carregado como trial (mesmo conteúdo, hash "
            f"{video.content_hash[:12]}…), possivelmente com outro nome de arquivo.",
        )
        raise
    except psycopg.errors.ForeignKeyViolation:
        _fail(
            dsn, job.id, f"Experimento #{experiment_id} ou montagem #{maze_config_id} não existe."
        )
        raise

    with get_connection(dsn) as conn:
        mark_finished(conn, job.id, execucao_id=None)
    return {"trial_id": trial_id}


def _fail(dsn: str | None, rq_job_id: str, message: str) -> None:
    with get_connection(dsn) as conn:
        mark_failed(conn, rq_job_id, message)
