"""Read a reference frame without changing the original video."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray


def read_reference_frame(video_path: str | Path, frame_index: int = 0) -> NDArray[np.uint8]:
    """Decode a zero-based reference frame and always release the capture.

    A local, readable video and a nonnegative integer frame index are required.
    Failed seeking is an error, so an unintended frame is never silently used.
    """
    if isinstance(frame_index, bool) or not isinstance(frame_index, int) or frame_index < 0:
        raise ValueError("O índice do quadro deve ser um inteiro maior ou igual a zero.")
    path = Path(video_path)
    if not path.is_file():
        raise ValueError(f"Arquivo de vídeo não encontrado: {path}")
    capture = None
    try:
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise ValueError(f"Não foi possível abrir o vídeo: {path}")
        if frame_index and not capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index):
            raise ValueError(f"Não foi possível acessar o quadro {frame_index} do vídeo: {path}")
        ok, frame = capture.read()
        if not ok or frame is None or frame.size == 0:
            raise ValueError(f"Não foi possível ler o quadro {frame_index} do vídeo: {path}")
        return frame
    except cv2.error as exc:
        raise ValueError(f"Erro ao decodificar o vídeo {path}: {exc}") from exc
    finally:
        if capture is not None:
            capture.release()
