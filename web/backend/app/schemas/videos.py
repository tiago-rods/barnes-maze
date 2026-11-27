"""Modelos para o passo "carregar vídeo" do wizard (US-01/03)."""

from __future__ import annotations

from pydantic import BaseModel

from .trials import TrialInterval


class VideoSummary(BaseModel):
    path: str
    name: str


class PickVideoRequest(BaseModel):
    initial_dir: str | None = None


class PickVideoResponse(BaseModel):
    path: str


class InspectRequest(BaseModel):
    path: str
    start_s: float | None = None
    end_s: float | None = None


class VideoInfo(BaseModel):
    path: str
    width: int
    height: int
    frame_count: int
    fps_declared: float
    fps_real: float
    duration_s: float
    fps_is_variable: bool
    content_hash: str
    interval: TrialInterval
