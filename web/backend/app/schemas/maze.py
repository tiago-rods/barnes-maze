"""Modelos para o passo "criar montagem" do wizard (US-04)."""

from __future__ import annotations

from pydantic import BaseModel


class HoleSchema(BaseModel):
    hole_number: int
    angle_deg: float
    x_px: float
    y_px: float
    radius_px: float
    is_target: bool


class MazeGeometrySchema(BaseModel):
    center_x_px: float
    center_y_px: float
    platform_radius_px: float
    holes: list[HoleSchema]


class Circle(BaseModel):
    center_x_px: float
    center_y_px: float
    radius_px: float


class DetectFrameRequest(BaseModel):
    video_path: str
    frame_index: int = 0


class DetectHolesRingRequest(DetectFrameRequest):
    expected_hole_area_fraction: float


class GenerateGeometryRequest(BaseModel):
    center_x_px: float
    center_y_px: float
    platform_radius_px: float
    hole_count: int
    start_angle_deg: float
    target_hole_number: int
    hole_radius_px: float


class SnapHolesRequest(BaseModel):
    geometry: MazeGeometrySchema
    video_path: str
    frame_index: int = 0
    expected_hole_area_fraction: float
    max_offset_px: float


class SnapHolesResponse(BaseModel):
    geometry: MazeGeometrySchema
    snapped_count: int


class CreateMazeRequest(BaseModel):
    experiment_id: int
    name: str
    arena_diameter_cm: float
    hole_diameter_cm: float
    geometry: MazeGeometrySchema


class CreateMazeResponse(BaseModel):
    maze_config_id: int
