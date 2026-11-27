"""Modelo para o passo "métricas de deslocamento" do wizard (US-18)."""

from __future__ import annotations

from pydantic import BaseModel


class DisplacementRequest(BaseModel):
    trial_id: int
    ponto: str = "centro_corpo"
