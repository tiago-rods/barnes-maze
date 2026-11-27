"""Estado em memória da revisão de pose (US-10), equivalente web de `barnes pose review`.

Como a janela OpenCV, a revisão parte do primeiro trecho pendente e lê os
quadros necessários uma única vez. Aqui, esse estado (`ReviewSession` +
`ReviewFrames` + overlay) fica vivo no processo do FastAPI entre
requisições — um dicionário por trial, sem pool nem banco: concorrência
não é um problema real para uma ferramenta local de um único usuário.
Nada é persistido até `/save`; descartar a sessão (`/cancel` ou reiniciar o
processo) equivale a fechar a janela com Esc hoje.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2

from barnes.cli import _load_series_inputs, _review_overlay, _review_video, _SeriesInputs
from barnes.db.connection import get_connection
from barnes.db.executions import get_execution
from barnes.db.trials import get_trial
from barnes.pose.quality import segments_from_report
from barnes.pose.review_ui import ReviewFrames, ReviewSession, load_review_frames
from barnes.pose.trajectory import POSTPROCESSING_KEY, read_metadata, read_trajectory


@dataclass
class ReviewState:
    session: ReviewSession
    frames: ReviewFrames
    overlay: dict[int, dict[str, tuple[float, float]]]
    inputs: _SeriesInputs
    destination: Path
    generator_execucao_id: int


_SESSIONS: dict[int, ReviewState] = {}


def bootstrap(
    trial_id: int, *, include_reviewed: bool, margin: int, dsn: str | None
) -> ReviewState:
    """Reproduz o bootstrap de `cli.py`'s `pose review` e guarda o estado por trial.

    Raises:
        ValueError: Mesmas condições da CLI (sem série, sem pós-processamento,
            execução geradora sem inferência registrada, nada pendente).
    """
    with get_connection(dsn) as conn:
        stored = get_trial(conn, trial_id)
    if stored.trajectory_path is None:
        raise ValueError(
            f"O trial #{trial_id} ainda não tem série de pose: gere a série antes da revisão."
        )
    current = read_trajectory(stored.trajectory_path)
    meta = read_metadata(current)
    report = meta.get(POSTPROCESSING_KEY)
    if report is None:
        raise ValueError(
            f"A série atual do trial #{trial_id} foi gerada sem o pós-processamento (US-10): "
            "gere a série de novo."
        )
    segments = [s for s in segments_from_report(report) if include_reviewed or s.pending]
    if not segments:
        kind = "sinalizado" if include_reviewed else "pendente de revisão"
        raise ValueError(f"Nenhum trecho {kind} no trial #{trial_id}.")
    with get_connection(dsn) as conn:
        generator = get_execution(conn, meta["execucao_id"])
    inference = (generator.parametros or {}).get("inference_run")
    if not inference:
        raise ValueError(
            f"A execução #{meta['execucao_id']} não registra a inferência usada: "
            "gere a série de novo."
        )
    inputs = _load_series_inputs(trial_id, Path(inference), dsn)
    source_video = _review_video(stored, None)
    quadros = current.column("quadro").to_numpy()
    session = ReviewSession(
        segments, first_frame=int(quadros[0]), last_frame=int(quadros[-1]), margin=margin
    )
    wanted = session.frames_to_load()
    frames = load_review_frames(source_video, wanted)
    overlay = _review_overlay(current, meta["cm_per_px"], set(wanted))
    state = ReviewState(
        session=session,
        frames=frames,
        overlay=overlay,
        inputs=inputs,
        destination=Path(stored.trajectory_path),
        generator_execucao_id=meta["execucao_id"],
    )
    _SESSIONS[trial_id] = state
    return state


def get_state(trial_id: int) -> ReviewState:
    """Raises: KeyError se não há revisão em andamento para o trial."""
    state = _SESSIONS.get(trial_id)
    if state is None:
        raise KeyError(f"Nenhuma revisão em andamento para o trial #{trial_id}.")
    return state


def discard(trial_id: int) -> None:
    _SESSIONS.pop(trial_id, None)


def encode_frame_jpeg(state: ReviewState, frame_index: int) -> bytes | None:
    """`None` se o quadro não estiver entre os carregados (fora da margem, ou vídeo mais curto)."""
    preview = state.frames.previews.get(frame_index)
    if preview is None:
        return None
    ok, buffer = cv2.imencode(".jpg", preview)
    return buffer.tobytes() if ok else None
