"""Modelos para os passos de pose do wizard (US-07/08/09/10)."""

from __future__ import annotations

from pydantic import BaseModel


class InferRequest(BaseModel):
    model_dir: str
    trial_id: int
    video_path: str | None = None
    out_dir: str = "data/pose/inference"
    device: str = "cpu"
    batch_size: int = 4


class SeriesRequest(BaseModel):
    trial_id: int
    inference_dir: str
    out_dir: str = "data/interim"
