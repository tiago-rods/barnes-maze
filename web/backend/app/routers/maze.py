"""Equivalente web de `barnes maze create`: detecção + geometria + persistência (US-04).

A janela OpenCV interativa (`cli.py`) fica de fora; os cinco cálculos puros
por trás dela (`barnes.geometry.builder`) e `generate_holes` são os mesmos
chamados aqui — só a interação (arrastar/clicar) muda para o canvas React.
"""

from __future__ import annotations

import numpy as np
import psycopg
from fastapi import APIRouter, Depends, HTTPException

from barnes.db.maze_configs import get_maze_config, insert_maze_config
from barnes.geometry.builder import (
    detect_hole_candidates,
    detect_holes_ring,
    detect_platform_circle,
    snap_holes_to_detected_centers,
)
from barnes.geometry.holes import Hole, MazeGeometry, generate_holes
from barnes.geometry.validation import GeometryValidationError
from barnes.io.video import VideoLoadError, read_frame

from ..deps import get_db
from ..schemas.maze import (
    Circle,
    CreateMazeRequest,
    CreateMazeResponse,
    DetectFrameRequest,
    DetectHolesRingRequest,
    GenerateGeometryRequest,
    MazeGeometrySchema,
    SnapHolesRequest,
    SnapHolesResponse,
)

router = APIRouter(prefix="/api/maze", tags=["maze"])


def _to_schema(geometry: MazeGeometry) -> MazeGeometrySchema:
    return MazeGeometrySchema.model_validate(geometry, from_attributes=True)


def _from_schema(geometry: MazeGeometrySchema) -> MazeGeometry:
    return MazeGeometry(
        center_x_px=geometry.center_x_px,
        center_y_px=geometry.center_y_px,
        platform_radius_px=geometry.platform_radius_px,
        holes=tuple(Hole(**hole.model_dump()) for hole in geometry.holes),
    )


def _read_frame(video_path: str, frame_index: int) -> np.ndarray:
    try:
        return read_frame(video_path, frame_index)
    except VideoLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/detect-platform", response_model=Circle | None)
def detect_platform(request: DetectFrameRequest) -> Circle | None:
    frame = _read_frame(request.video_path, request.frame_index)
    detected = detect_platform_circle(frame)
    if detected is None:
        return None
    center_x, center_y, radius = detected
    return Circle(center_x_px=center_x, center_y_px=center_y, radius_px=radius)


@router.post("/detect-holes", response_model=Circle | None)
def detect_holes(request: DetectHolesRingRequest) -> Circle | None:
    frame = _read_frame(request.video_path, request.frame_index)
    detected = detect_holes_ring(frame, request.expected_hole_area_fraction)
    if detected is None:
        return None
    center_x, center_y, radius = detected
    return Circle(center_x_px=center_x, center_y_px=center_y, radius_px=radius)


@router.post("/geometry", response_model=MazeGeometrySchema)
def compute_geometry(request: GenerateGeometryRequest) -> MazeGeometrySchema:
    try:
        geometry = generate_holes(**request.model_dump())
    except GeometryValidationError as exc:
        raise HTTPException(status_code=422, detail=f"{exc.field}: {exc}") from exc
    return _to_schema(geometry)


@router.post("/snap-holes", response_model=SnapHolesResponse)
def snap_holes(request: SnapHolesRequest) -> SnapHolesResponse:
    frame = _read_frame(request.video_path, request.frame_index)
    candidates = detect_hole_candidates(frame, request.expected_hole_area_fraction)
    snapped, count = snap_holes_to_detected_centers(
        _from_schema(request.geometry), candidates, request.max_offset_px
    )
    return SnapHolesResponse(geometry=_to_schema(snapped), snapped_count=count)


@router.post("", response_model=CreateMazeResponse)
def create_maze(
    request: CreateMazeRequest, conn: psycopg.Connection = Depends(get_db)
) -> CreateMazeResponse:
    try:
        maze_config_id = insert_maze_config(
            conn,
            experiment_id=request.experiment_id,
            name=request.name,
            arena_diameter_cm=request.arena_diameter_cm,
            hole_diameter_cm=request.hole_diameter_cm,
            geometry=_from_schema(request.geometry),
        )
    except psycopg.errors.ForeignKeyViolation as exc:
        raise HTTPException(
            status_code=400, detail=f"Experimento #{request.experiment_id} não existe."
        ) from exc
    return CreateMazeResponse(maze_config_id=maze_config_id)


@router.get("/{maze_config_id}", response_model=MazeGeometrySchema)
def get_maze(
    maze_config_id: int, conn: psycopg.Connection = Depends(get_db)
) -> MazeGeometrySchema:
    try:
        geometry = get_maze_config(conn, maze_config_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_schema(geometry)
