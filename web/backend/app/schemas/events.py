"""Modelo para o passo "detectar eventos" do wizard (US-11/12/13)."""

from __future__ import annotations

from pydantic import BaseModel


class EnterRequest(BaseModel):
    trial_id: int
    config: str | None = None
    out_dir: str = "data/events"
