"""Modelos para o passo "calibrar escala" do wizard (US-02)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

Point = tuple[float, float]


class SegmentSchema(BaseModel):
    start: Point
    end: Point
    length_cm: float


class CalibrateRequest(BaseModel):
    maze_config_id: int
    video_path: str
    frame_index: int = 0
    segment_1: tuple[Point, Point]
    segment_2: tuple[Point, Point]
    length_1_cm: float
    length_2_cm: float


class CalibrateResponse(BaseModel):
    cm_per_px: float
    relative_disagreement: float
    angle_degrees: float


class VerifyRequest(BaseModel):
    maze_config_id: int
    video_path: str
    frame_index: int = 0
    segment: tuple[Point, Point]
    length_cm: float


class VerifyResponse(BaseModel):
    measured_cm: float
    known_cm: float
    relative_error: float
    accepted: bool


class CalibrationSchema(BaseModel):
    cm_per_px: float
    calibration_date: date
    measured_error_pct: float | None
    segments: list[SegmentSchema]
    reference_video: str | None
    reference_frame: int | None
    reference_width: int | None
    reference_height: int | None
