"""Equivalente web de `barnes scale calibrate`/`verify`/`show` (US-02).

A janela OpenCV (`io.calibration_ui.collect_segments`) fica de fora — o
canvas React coleta os cliques e envia os pontos já prontos; o cálculo em
si (`io.calibration`) e a persistência (`db.calibration`) são os mesmos
que a CLI usa.
"""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends, HTTPException

from barnes.db.calibration import (
    get_calibration,
    save_calibration,
    save_verification,
    validate_frame_size,
)
from barnes.io.calibration import (
    CalibrationError,
    CalibrationResult,
    Segment,
    calculate_calibration,
    verify_distance,
)
from barnes.io.video import VideoLoadError, read_frame

from ..deps import get_db
from ..schemas.scale import (
    CalibrateRequest,
    CalibrateResponse,
    CalibrationSchema,
    VerifyRequest,
    VerifyResponse,
)

router = APIRouter(prefix="/api/scale", tags=["scale"])


def _read_frame(video_path: str, frame_index: int):
    try:
        return read_frame(video_path, frame_index)
    except VideoLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/calibrate", response_model=CalibrateResponse)
def calibrate(
    request: CalibrateRequest, conn: psycopg.Connection = Depends(get_db)
) -> CalibrateResponse:
    frame = _read_frame(request.video_path, request.frame_index)
    try:
        segment_1 = Segment(request.segment_1[0], request.segment_1[1], request.length_1_cm)
        segment_2 = Segment(request.segment_2[0], request.segment_2[1], request.length_2_cm)
        result = calculate_calibration([segment_1, segment_2])
    except CalibrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        save_calibration(
            conn,
            request.maze_config_id,
            result,
            reference_video=request.video_path,
            reference_frame=request.frame_index,
            reference_size=(frame.shape[1], frame.shape[0]),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CalibrateResponse(
        cm_per_px=result.cm_per_px,
        relative_disagreement=result.relative_disagreement,
        angle_degrees=result.angle_degrees,
    )


@router.post("/verify", response_model=VerifyResponse)
def verify(request: VerifyRequest, conn: psycopg.Connection = Depends(get_db)) -> VerifyResponse:
    frame = _read_frame(request.video_path, request.frame_index)
    try:
        calibration = get_calibration(conn, request.maze_config_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if calibration is None:
        raise HTTPException(
            status_code=400,
            detail=f"A montagem {request.maze_config_id} exige calibração antes da verificação.",
        )
    try:
        validate_frame_size(calibration, (frame.shape[1], frame.shape[0]))
        independent = Segment(request.segment[0], request.segment[1], request.length_cm)
        reconstructed = CalibrationResult(
            segments=calibration.segments,
            cm_per_px=calibration.cm_per_px,
            relative_disagreement=0.0,
            angle_degrees=0.0,
        )
        verification = verify_distance(reconstructed, independent)
    except (CalibrationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    save_verification(conn, request.maze_config_id, verification.relative_error)
    return VerifyResponse(
        measured_cm=verification.measured_cm,
        known_cm=verification.known_cm,
        relative_error=verification.relative_error,
        accepted=verification.accepted,
    )


@router.get("/{maze_config_id}", response_model=CalibrationSchema | None)
def get_scale(
    maze_config_id: int, conn: psycopg.Connection = Depends(get_db)
) -> CalibrationSchema | None:
    try:
        calibration = get_calibration(conn, maze_config_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if calibration is None:
        return None
    return CalibrationSchema.model_validate(calibration, from_attributes=True)
