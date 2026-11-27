"""Modelos para `GET /api/learning-curves` (US-22)."""

from __future__ import annotations

from pydantic import BaseModel


class MetricInfo(BaseModel):
    key: str
    label: str


class AnimalPoint(BaseModel):
    animal_id: int
    session: int
    mean: float
    n_trials: int


class AggregatePoint(BaseModel):
    session: int
    mean: float
    sd: float | None
    n_animals: int


class LearningCurves(BaseModel):
    animals: list[AnimalPoint]
    aggregate: list[AggregatePoint]
