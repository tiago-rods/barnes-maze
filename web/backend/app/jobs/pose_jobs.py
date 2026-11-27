"""Jobs RQ: inferência de pose (US-07/08) e série de trajetória (US-09/10).

Mesma sequência que `cli_pose.py`'s `infer` e `cli.py`'s `pose series` já
executam — incluindo a persistência de artefatos mesmo quando o Postgres
está indisponível (`_persist_or_explain`) — só que no processo do worker
RQ em vez do processo da CLI.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from rq import get_current_job

from barnes.cli import _load_series_inputs, _write_series
from barnes.cli_pose import _persist_or_explain
from barnes.db.calibration import require_calibration
from barnes.db.connection import get_connection
from barnes.db.jobs import mark_failed, mark_finished, mark_started
from barnes.db.maze_configs import get_maze_config
from barnes.db.pose_corrections import REVIEW_COMMAND
from barnes.db.pose_executions import get_inference_trial
from barnes.pose.inference import InferenceError, infer_trial
from barnes.pose.quality import PointCorrection
from barnes.pose.trajectory import trajectory_path

from ..demo_pose import ensure_demo_model, synthetic_backend_factory
from .events_jobs import run_events_enter
from .tracking import enqueue_tracked

logger = logging.getLogger(__name__)


def _fail(dsn: str | None, rq_job_id: str, message: str) -> None:
    with get_connection(dsn) as conn:
        mark_failed(conn, rq_job_id, message)


def _infer_and_chain(
    job_id: str,
    *,
    model_dir: str | Path,
    trial_id: int,
    video_path: str | None,
    out_dir: str,
    device: str,
    batch_size: int,
    dsn: str | None,
    backend_factory=None,
) -> dict:
    """Inferência (real ou demo) + registro + próximo elo do pipeline (série)."""
    try:
        with get_connection(dsn) as conn:
            stored = get_inference_trial(conn, trial_id)
        run_dir = infer_trial(
            model_dir,
            video_path or stored.filepath,
            out_dir,
            trial_id=trial_id,
            maze_config_id=stored.maze_config_id,
            interval=stored.interval,
            expected_content_hash=stored.content_hash,
            fps=stored.fps_real,
            frame_count=stored.frame_count,
            width=stored.width_px,
            height=stored.height_px,
            device=device,
            batch_size=batch_size,
            backend_factory=backend_factory,
        )
        execucao_id = _persist_or_explain(run_dir, "inferencia", dsn)
    except InferenceError as exc:
        if getattr(exc, "run_dir", None):
            try:
                _persist_or_explain(exc.run_dir, "inferencia", dsn)
            except Exception:  # o erro original da inferência é o que importa
                logger.exception("Falha ao registrar a inferência que falhou em %s", exc.run_dir)
        _fail(dsn, job_id, str(exc))
        raise
    except Exception as exc:
        _fail(dsn, job_id, f"{type(exc).__name__}: {exc}")
        raise

    with get_connection(dsn) as conn:
        mark_finished(conn, job_id, execucao_id)

    # Pipeline automático (sem intervenção do operador): série -> eventos ->
    # métricas consolidadas. Cada elo só enfileira o próximo depois do seu
    # próprio sucesso.
    enqueue_tracked(
        run_pose_series,
        {"trial_id": trial_id, "inference_dir": str(run_dir), "dsn": dsn},
        kind="pose_series",
        trial_id=trial_id,
    )
    return {"execucao_id": execucao_id, "run_dir": str(run_dir)}


def run_pose_infer(
    *,
    model_dir: str,
    trial_id: int,
    video_path: str | None = None,
    out_dir: str = "data/pose/inference",
    device: str = "cpu",
    batch_size: int = 4,
    dsn: str | None = None,
) -> dict:
    job = get_current_job()
    with get_connection(dsn) as conn:
        mark_started(conn, job.id)
    return _infer_and_chain(
        job.id,
        model_dir=model_dir,
        trial_id=trial_id,
        video_path=video_path,
        out_dir=out_dir,
        device=device,
        batch_size=batch_size,
        dsn=dsn,
    )


def run_pose_demo(
    *,
    trial_id: int,
    out_dir: str = "data/pose/inference",
    dsn: str | None = None,
) -> dict:
    """Inferência com o backend SINTÉTICO de demonstração (`app.demo_pose`).

    Passa pelo `infer_trial` real (hash do vídeo, intervalo útil, registro
    `execucao`); só a pose em si é gerada por regra, não por modelo.
    """
    job = get_current_job()
    with get_connection(dsn) as conn:
        mark_started(conn, job.id)
    try:
        with get_connection(dsn) as conn:
            stored = get_inference_trial(conn, trial_id)
            geometry = get_maze_config(conn, stored.maze_config_id)
            cm_per_px = require_calibration(conn, stored.maze_config_id).cm_per_px
        model_dir = ensure_demo_model(stored.maze_config_id)
        factory = synthetic_backend_factory(geometry, cm_per_px, stored.fps_real)
    except Exception as exc:
        _fail(dsn, job.id, f"{type(exc).__name__}: {exc}")
        raise
    return _infer_and_chain(
        job.id,
        model_dir=model_dir,
        trial_id=trial_id,
        video_path=None,
        out_dir=out_dir,
        device="cpu",
        batch_size=16,
        dsn=dsn,
        backend_factory=factory,
    )


def run_pose_series(
    *,
    trial_id: int,
    inference_dir: str,
    out_dir: str = "data/interim",
    dsn: str | None = None,
) -> dict:
    job = get_current_job()
    with get_connection(dsn) as conn:
        mark_started(conn, job.id)

    started_at = datetime.now(UTC)
    try:
        inputs = _load_series_inputs(trial_id, Path(inference_dir), dsn)
        destination = trajectory_path(out_dir, trial_id)
        written = _write_series(
            inputs, destination=destination, started_at=started_at, dsn=dsn, command="pose series"
        )
    except Exception as exc:
        _fail(dsn, job.id, str(exc))
        raise

    with get_connection(dsn) as conn:
        mark_finished(conn, job.id, written.execucao_id)

    # Continuação automática: eventos; as métricas consolidadas vêm depois
    # deles (precisam da sequência de visitação).
    enqueue_tracked(
        run_events_enter, {"trial_id": trial_id, "dsn": dsn}, kind="events_enter", trial_id=trial_id
    )

    table = written.table
    without_pose = table.num_rows - sum(table.column("pose_valida").to_pylist())
    return {
        "execucao_id": written.execucao_id,
        "destination": str(destination),
        "frames": table.num_rows,
        "frames_without_pose": without_pose,
    }


def run_pose_review_save(
    *,
    trial_id: int,
    inference_dir: str,
    destination: str,
    corrections: list[dict],
    reviewed_segments: list[list[int]],
    generator_execucao_id: int,
    dsn: str | None = None,
) -> dict:
    """Regenera a série do trial com as correções/trechos revisados da sessão web (US-10).

    A sessão de revisão (`app.pose_review_state.ReviewState`) vive no
    processo do FastAPI, não no worker — por isso recebe aqui só o
    resultado já serializável (`ReviewSession.result()`), não o objeto
    vivo, e relê `_load_series_inputs` do zero (barato: sem GPU).
    """
    job = get_current_job()
    with get_connection(dsn) as conn:
        mark_started(conn, job.id)

    started_at = datetime.now(UTC)
    try:
        inputs = _load_series_inputs(trial_id, Path(inference_dir), dsn)
        new_corrections = tuple(
            PointCorrection(c["frame"], c["point"], c["x_px"], c["y_px"]) for c in corrections
        )
        new_reviewed = tuple(tuple(pair) for pair in reviewed_segments)
        written = _write_series(
            inputs,
            destination=Path(destination),
            started_at=started_at,
            dsn=dsn,
            command=REVIEW_COMMAND,
            extra_parameters={
                "trechos_revisados": [{"inicio": s, "fim": e} for s, e in new_reviewed],
                "correcoes_novas": len(new_corrections),
                "serie_anterior_execucao_id": generator_execucao_id,
            },
            new_corrections=new_corrections,
            new_reviewed=new_reviewed,
        )
    except Exception as exc:
        _fail(dsn, job.id, str(exc))
        raise

    with get_connection(dsn) as conn:
        mark_finished(conn, job.id, written.execucao_id)
    return {"execucao_id": written.execucao_id, "destination": destination}
