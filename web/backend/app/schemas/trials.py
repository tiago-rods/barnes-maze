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


class LoadTrialRequest(BaseModel):
    path: str
    experiment_id: int
    maze_config_id: int
    phase: str
    day_number: int
    trial_number_in_day: int
    rotation_deg: float = 0.0
    start_s: float | None = None
    end_s: float | None = None


class JobEnqueued(BaseModel):
    job_id: int


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
