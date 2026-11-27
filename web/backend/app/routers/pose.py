"""`POST /api/pose/infer`, `/demo` e `/series` — enfileiram os jobs de pose (US-07/08/09/10).

`/demo` usa a pose SINTÉTICA de `app.demo_pose` (sem modelo treinado) para
demonstrar o pipeline; o resultado fica marcado como DEMO na proveniência.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..jobs.pose_jobs import run_pose_demo, run_pose_infer, run_pose_series
from ..jobs.tracking import enqueue_tracked
from ..schemas.jobs import JobEnqueued
from ..schemas.pose import DemoRequest, InferRequest, SeriesRequest

router = APIRouter(prefix="/api/pose", tags=["pose"])


@router.post("/infer", response_model=JobEnqueued, status_code=202)
def infer(request: InferRequest) -> JobEnqueued:
    job_id = enqueue_tracked(
        run_pose_infer, request.model_dump(), kind="pose_infer", trial_id=request.trial_id
    )
    return JobEnqueued(job_id=job_id)


@router.post("/demo", response_model=JobEnqueued, status_code=202)
def demo(request: DemoRequest) -> JobEnqueued:
    job_id = enqueue_tracked(
        run_pose_demo, request.model_dump(), kind="pose_demo", trial_id=request.trial_id
    )
    return JobEnqueued(job_id=job_id)


@router.post("/series", response_model=JobEnqueued, status_code=202)
def series(request: SeriesRequest) -> JobEnqueued:
    job_id = enqueue_tracked(
        run_pose_series, request.model_dump(), kind="pose_series", trial_id=request.trial_id
    )
    return JobEnqueued(job_id=job_id)
