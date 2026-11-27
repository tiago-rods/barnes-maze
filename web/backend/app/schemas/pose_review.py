"""Modelos para o passo "revisar pose" do wizard (US-10)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SegmentSchema(BaseModel):
    start_frame: int
    end_frame: int
    missing_points: list[str]
    pending: bool
    confirmed: bool


class PointXY(BaseModel):
    x_px: float
    y_px: float


class ReviewStateSchema(BaseModel):
    trial_id: int
    segments: list[SegmentSchema]
    segment_index: int
    frame: int
    view_range: tuple[int, int]
    point: str
    ratio: float
    marks: dict[str, PointXY]
    overlay: dict[str, PointXY]


class NavigateRequest(BaseModel):
    action: Literal["next_segment", "previous_segment", "next_frame", "previous_frame"]


class SelectPointRequest(BaseModel):
    point: str


class MarkRequest(BaseModel):
    x_px: float
    y_px: float
