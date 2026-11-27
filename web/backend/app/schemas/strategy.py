"""Modelo para o passo "classificar estratégia" do wizard (US-20)."""

from __future__ import annotations

from pydantic import BaseModel


class ClassifyRequest(BaseModel):
    trial_id: int
    config: str | None = None
    out_dir: str = "data/strategy"
