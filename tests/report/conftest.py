from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from barnes.io.trim import interval_from_seconds
from barnes.pose.series import PoseFrames, build_series

FPS = 10.0
N_FRAMES = 101
NOSE_OFFSET = 1.0


@pytest.fixture
def straight_line_trajectory():
    frames = np.arange(N_FRAMES)
    centro_x = frames.astype(np.float64)
    centro_y = np.zeros(N_FRAMES)
    focinho_x = centro_x + NOSE_OFFSET
    focinho_y = centro_y
    cauda_x = centro_x - NOSE_OFFSET
    cauda_y = centro_y
    conf = np.ones(N_FRAMES)

    pose = PoseFrames(
        frames=frames,
        x_px={"focinho": focinho_x, "centro_corpo": centro_x, "base_cauda": cauda_x},
        y_px={"focinho": focinho_y, "centro_corpo": centro_y, "base_cauda": cauda_y},
        confidence={"focinho": conf, "centro_corpo": conf, "base_cauda": conf},
    )
    interval = interval_from_seconds(0.0, (N_FRAMES - 1) / FPS, FPS, manually_adjusted=True)
    return build_series(
        pose,
        trial_id=1,
        execucao_id=1,
        expected_frames=(0, N_FRAMES - 1),
        fps=FPS,
        interval=interval,
        fps_variable=False,
        cm_per_px=1.0,
        content_hash="straight-line",
        model_id="synthetic-report-test",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
