"""Apoio ao passo "carregar vídeo" do wizard: listar, inspecionar e pré-visualizar (US-01/03).

Nenhum upload HTTP de propósito — frontend e backend compartilham o mesmo
sistema de arquivos (ferramenta local), então videos grandes não precisam
trafegar pela rede; o wizard só lista/referencia caminhos.
"""

from __future__ import annotations

from pathlib import Path

import cv2
from fastapi import APIRouter, HTTPException, Response

from barnes.io.trim import TrialIntervalError, build_trial_interval
from barnes.io.video import VideoLoadError, load_trial_video, read_frame

from ..config import VIDEO_DATA_DIR
from ..schemas.trials import TrialInterval as TrialIntervalSchema
from ..schemas.videos import InspectRequest, VideoInfo, VideoSummary

router = APIRouter(prefix="/api/videos", tags=["videos"])


@router.get("", response_model=list[VideoSummary])
def list_videos(dir: str | None = None) -> list[VideoSummary]:
    root = Path(dir) if dir else VIDEO_DATA_DIR
    if not root.is_dir():
        raise HTTPException(status_code=404, detail=f"Diretório não encontrado: {root}")
    return [VideoSummary(path=str(path), name=path.name) for path in sorted(root.glob("*.mp4"))]


@router.post("/inspect", response_model=VideoInfo)
def inspect_video(request: InspectRequest) -> VideoInfo:
    try:
        video = load_trial_video(request.path)
        interval = build_trial_interval(video, start_s=request.start_s, end_s=request.end_s)
    except VideoLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TrialIntervalError as exc:
        raise HTTPException(status_code=400, detail=f"Erro no intervalo útil: {exc}") from exc
    return VideoInfo(
        path=str(video.path),
        width=video.width,
        height=video.height,
        frame_count=video.frame_count,
        fps_declared=video.fps_declared,
        fps_real=video.fps_real,
        duration_s=video.duration_s,
        fps_is_variable=video.fps_is_variable,
        content_hash=video.content_hash,
        interval=TrialIntervalSchema.model_validate(interval, from_attributes=True),
    )


@router.get("/frame")
def get_frame(path: str, frame_index: int = 0) -> Response:
    try:
        frame = read_frame(path, frame_index)
    except VideoLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ok, buffer = cv2.imencode(".jpg", frame)
    if not ok:
        raise HTTPException(status_code=500, detail="Falha ao codificar o quadro em JPEG.")
    return Response(content=buffer.tobytes(), media_type="image/jpeg")
