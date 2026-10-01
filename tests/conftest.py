"""Fixtures compartilhadas entre os testes."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest


def _write_synthetic_video(
    path: Path, frame_count: int, fps: float, size: tuple[int, int] = (64, 48)
) -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, size)
    try:
        for i in range(frame_count):
            frame = np.full((size[1], size[0], 3), i % 256, dtype=np.uint8)
            writer.write(frame)
    finally:
        writer.release()


@pytest.fixture
def make_mp4(tmp_path: Path):
    """Fábrica de vídeos .mp4 sintéticos e pequenos, para testes sem depender de data/."""

    def _make(name: str = "synthetic.mp4", frame_count: int = 10, fps: float = 10.0) -> Path:
        path = tmp_path / name
        _write_synthetic_video(path, frame_count, fps)
        return path

    return _make
