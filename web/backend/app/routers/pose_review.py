"""Equivalente web de `barnes pose review` (US-10): sessão em memória por trial.

A janela OpenCV (`pose.review_ui.collect_review`) fica de fora; o estado
(`ReviewSession`, já pura e separada do laço cv2) e a leitura dos quadros
(`load_review_frames`) são os mesmos que a CLI já usa — só a interação
muda para estes endpoints + o canvas React.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from .. import pose_review_state as review
from ..jobs.pose_jobs import run_pose_review_save
from ..jobs.tracking import enqueue_tracked
from ..schemas.jobs import JobEnqueued
from ..schemas.pose_review import (
    MarkRequest,
    NavigateRequest,
    PointXY,
    ReviewStateSchema,
    SegmentSchema,
    SelectPointRequest,
)

router = APIRouter(prefix="/api/pose/review", tags=["pose-review"])


def _require(trial_id: int) -> review.ReviewState:
    try:
        return review.get_state(trial_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _to_schema(trial_id: int, state: review.ReviewState) -> ReviewStateSchema:
    session = state.session
    frame = session.frame
    ratio = state.frames.ratio
    marks = {
        point: PointXY(x_px=xy[0] * ratio, y_px=xy[1] * ratio)
        for point, xy in session.marks_at(frame).items()
    }
    overlay = {
        point: PointXY(x_px=xy[0] * ratio, y_px=xy[1] * ratio)
        for point, xy in state.overlay.get(frame, {}).items()
    }
    segments = [
        SegmentSchema(
            start_frame=segment.start_frame,
            end_frame=segment.end_frame,
            missing_points=list(segment.missing_points),
            pending=segment.pending,
            confirmed=session.is_confirmed(index),
        )
        for index, segment in enumerate(session.segments)
    ]
    return ReviewStateSchema(
        trial_id=trial_id,
        segments=segments,
        segment_index=session.segment_index,
        frame=frame,
        view_range=session.view_range(),
        point=session.point,
        ratio=ratio,
        marks=marks,
        overlay=overlay,
    )


@router.get("/{trial_id}/segments", response_model=ReviewStateSchema)
def start_review(
    trial_id: int, include_reviewed: bool = False, margin: int = 10
) -> ReviewStateSchema:
    try:
        state = review.bootstrap(
            trial_id, include_reviewed=include_reviewed, margin=margin, dsn=None
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_schema(trial_id, state)


@router.get("/{trial_id}/frame/{frame_index}")
def get_frame(trial_id: int, frame_index: int) -> Response:
    state = _require(trial_id)
    data = review.encode_frame_jpeg(state, frame_index)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Quadro {frame_index} indisponível no vídeo.")
    return Response(content=data, media_type="image/jpeg")


@router.post("/{trial_id}/navigate", response_model=ReviewStateSchema)
def navigate(trial_id: int, request: NavigateRequest) -> ReviewStateSchema:
    state = _require(trial_id)
    actions = {
        "next_segment": state.session.next_segment,
        "previous_segment": state.session.previous_segment,
        "next_frame": state.session.next_frame,
        "previous_frame": state.session.previous_frame,
    }
    actions[request.action]()
    return _to_schema(trial_id, state)


@router.post("/{trial_id}/select-point", response_model=ReviewStateSchema)
def select_point(trial_id: int, request: SelectPointRequest) -> ReviewStateSchema:
    state = _require(trial_id)
    try:
        state.session.select_point(request.point)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_schema(trial_id, state)


@router.post("/{trial_id}/mark", response_model=ReviewStateSchema)
def mark(trial_id: int, request: MarkRequest) -> ReviewStateSchema:
    state = _require(trial_id)
    ratio = state.frames.ratio
    state.session.mark(request.x_px / ratio, request.y_px / ratio)
    return _to_schema(trial_id, state)


@router.post("/{trial_id}/undo", response_model=ReviewStateSchema)
def undo(trial_id: int) -> ReviewStateSchema:
    state = _require(trial_id)
    state.session.undo()
    return _to_schema(trial_id, state)


@router.post("/{trial_id}/confirm-segment", response_model=ReviewStateSchema)
def confirm_segment(trial_id: int) -> ReviewStateSchema:
    state = _require(trial_id)
    state.session.confirm_segment()
    return _to_schema(trial_id, state)


@router.post("/{trial_id}/cancel", status_code=204)
def cancel(trial_id: int) -> None:
    review.discard(trial_id)


@router.post("/{trial_id}/save", response_model=JobEnqueued, status_code=202)
def save(trial_id: int) -> JobEnqueued:
    state = _require(trial_id)
    result = state.session.result()
    if result.empty:
        review.discard(trial_id)
        raise HTTPException(
            status_code=400, detail="Nada marcado nem confirmado: nenhuma correção a salvar."
        )
    job_id = enqueue_tracked(
        run_pose_review_save,
        {
            "trial_id": trial_id,
            "inference_dir": str(state.inputs.inference),
            "destination": str(state.destination),
            "corrections": [
                {"frame": c.frame, "point": c.point, "x_px": c.x_px, "y_px": c.y_px}
                for c in result.corrections
            ],
            "reviewed_segments": [list(pair) for pair in result.reviewed_segments],
            "generator_execucao_id": state.generator_execucao_id,
        },
        kind="pose_review_save",
        trial_id=trial_id,
    )
    review.discard(trial_id)
    return JobEnqueued(job_id=job_id)
