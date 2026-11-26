"""Modelo de resposta para `GET /api/trials/{id}`."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class TrialInterval(BaseModel):
    start_s: float
    end_s: float
    start_frame: int
    end_frame: int
    manually_adjusted: bool


class Trial(BaseModel):
    id: int
    maze_config_id: int
    width_px: int
    height_px: int
    interval: TrialInterval | None
    filepath: Path | None
    content_hash: str | None
    file_size_bytes: int | None
    fps_real: float | None
    fps_is_variable: bool | None
    trajectory_path: Path | None
