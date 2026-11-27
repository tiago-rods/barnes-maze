"""FastAPI do wizard web + dashboard — desvio deliberado do backlog de cards (ver CLAUDE.md).

Importa `barnes.*` diretamente (mesmo venv, `uv sync --extra web`); nunca
chama a CLI via subprocess. Cada router é uma camada fina: recebe a
requisição, chama a mesma função que `cli.py`/`cli_*.py` já chamam, serializa
a resposta — nunca reimplementa lógica de geometria/pose/métricas aqui.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from barnes.db.connection import apply_migrations, get_connection

from .routers import (
    catalog,
    events,
    executions,
    experiments,
    jobs,
    learning,
    maze,
    metrics,
    pose,
    pose_review,
    report,
    scale,
    strategy,
    trials,
    videos,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    with get_connection() as conn:
        apply_migrations(conn)
    yield


app = FastAPI(title="Barnes Maze — Wizard & Dashboard", lifespan=lifespan)

app.include_router(experiments.router)
app.include_router(catalog.router)
app.include_router(trials.router)
app.include_router(executions.router)
app.include_router(jobs.router)
app.include_router(videos.router)
app.include_router(maze.router)
app.include_router(scale.router)
app.include_router(pose.router)
app.include_router(pose_review.router)
app.include_router(events.router)
app.include_router(metrics.router)
app.include_router(strategy.router)
app.include_router(learning.router)
app.include_router(report.router)
