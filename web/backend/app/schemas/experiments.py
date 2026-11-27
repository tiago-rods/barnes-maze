"""Modelos para `GET`/`POST /api/experiments`."""

from __future__ import annotations

from pydantic import BaseModel


class ExperimentSummary(BaseModel):
    id: int
    name: str
    description: str | None
    group_label: str | None
    animal_name: str | None = None


class CreateExperimentRequest(BaseModel):
    name: str
    description: str | None = None
    animal_name: str | None = None


class CreateSubjectRequest(BaseModel):
    name: str
    genotype: str | None = None


class CreateExperimentResponse(BaseModel):
    experiment_id: int
