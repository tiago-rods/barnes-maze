"""Modelos para `GET`/`POST /api/experiments`."""

from __future__ import annotations

from pydantic import BaseModel


class ExperimentSummary(BaseModel):
    id: int
    name: str
    description: str | None
    group_label: str | None


class CreateExperimentRequest(BaseModel):
    name: str
    description: str | None = None


class CreateExperimentResponse(BaseModel):
    experiment_id: int
