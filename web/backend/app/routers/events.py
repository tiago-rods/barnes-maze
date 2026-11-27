"""`POST /api/events/enter` — enfileira descoberta+entrada por buraco (US-11/12/13)."""

from __future__ import annotations

from fastapi import APIRouter

from ..jobs.events_jobs import run_events_enter
from ..jobs.tracking import enqueue_tracked
from ..schemas.events import EnterRequest
from ..schemas.jobs import JobEnqueued

router = APIRouter(prefix="/api/events", tags=["events"])


@router.post("/enter", response_model=JobEnqueued, status_code=202)
def enter(request: EnterRequest) -> JobEnqueued:
    job_id = enqueue_tracked(
        run_events_enter, request.model_dump(), kind="events_enter", trial_id=request.trial_id
    )
    return JobEnqueued(job_id=job_id)
