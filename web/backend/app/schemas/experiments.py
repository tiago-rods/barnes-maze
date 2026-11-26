"""Modelo de resposta para `GET /api/experiments`."""

from __future__ import annotations

from pydantic import BaseModel


class ExperimentSummary(BaseModel):
    id: int
    name: str
    description: str | None
    group_label: str | None
