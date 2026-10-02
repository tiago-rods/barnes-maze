"""Testes de src/barnes/io/trim.py (US-03)."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from barnes.io.trim import (
    TrialInterval,
    TrialIntervalError,
    build_trial_interval,
    detect_release_time,
    is_within_interval,
    seconds_from_trial_start,
    trimmed_frame_range,
)
from barnes.io.video import load_trial_video

FPS = 10.0
SIZE = (64, 48)  # (width, height)
STATIC_FRAMES = 10  # quadros parados antes da soltura
MOVING_FRAMES = 15  # quadros com o "animal" (círculo) em movimento


def _write_release_video(path: Path) -> None:
    """Vídeo sintético: quadros parados, depois um círculo que se move a cada quadro.

    Simula a soltura do animal (RN03): nada muda até o quadro `STATIC_FRAMES`,
    a partir daí um objeto em movimento contínuo entra em cena.
    """
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, FPS, SIZE)
    try:
        for i in range(STATIC_FRAMES):
            frame = np.zeros((SIZE[1], SIZE[0], 3), dtype=np.uint8)
            writer.write(frame)
        for i in range(MOVING_FRAMES):
            frame = np.zeros((SIZE[1], SIZE[0], 3), dtype=np.uint8)
            x = 5 + i * 3
            cv2.circle(frame, (min(x, SIZE[0] - 1), SIZE[1] // 2), 4, (255, 255, 255), -1)
            writer.write(frame)
    finally:
        writer.release()


def _write_static_video(path: Path, frame_count: int = 8) -> None:
    """Vídeo sintético sem nenhum movimento — detecção deve falhar (retornar None)."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, FPS, SIZE)
    try:
        for _ in range(frame_count):
            writer.write(np.zeros((SIZE[1], SIZE[0], 3), dtype=np.uint8))
    finally:
        writer.release()


@pytest.fixture
def release_video(tmp_path: Path) -> Path:
    path = tmp_path / "release.mp4"
    _write_release_video(path)
    return path


# --- detect_release_time --------------------------------------------------


def test_detect_release_time_finds_the_movement_onset(release_video: Path) -> None:
    detected = detect_release_time(str(release_video))

    assert detected is not None
    # Soltura simulada no quadro STATIC_FRAMES (10), a 10fps = 1.0s.
    assert detected == pytest.approx(STATIC_FRAMES / FPS, abs=0.15)


def test_detect_release_time_returns_none_without_movement(tmp_path: Path) -> None:
    path = tmp_path / "static.mp4"
    _write_static_video(path)

    assert detect_release_time(str(path)) is None


def test_detect_release_time_returns_none_for_too_short_video(tmp_path: Path) -> None:
    path = tmp_path / "short.mp4"
    _write_static_video(path, frame_count=3)

    assert detect_release_time(str(path)) is None


# --- build_trial_interval --------------------------------------------------


def test_build_trial_interval_auto_detects_start_and_confirms_is_not_manual(
    release_video: Path,
) -> None:
    video = load_trial_video(release_video)

    interval = build_trial_interval(video)

    assert interval.manually_adjusted is False
    assert interval.start_s == pytest.approx(STATIC_FRAMES / FPS, abs=0.15)
    assert interval.end_s == pytest.approx(video.duration_s)
    assert interval.start_frame == round(interval.start_s * video.fps_real)
    assert interval.end_frame == round(interval.end_s * video.fps_real)


def test_build_trial_interval_falls_back_to_zero_without_detected_movement(
    tmp_path: Path,
) -> None:
    path = tmp_path / "static.mp4"
    _write_static_video(path)
    video = load_trial_video(path)

    interval = build_trial_interval(video)

    assert interval.start_s == 0.0
    assert interval.manually_adjusted is False


def test_build_trial_interval_manual_override_marks_manually_adjusted(
    release_video: Path,
) -> None:
    video = load_trial_video(release_video)

    interval = build_trial_interval(video, start_s=0.3, end_s=2.0)

    assert interval.manually_adjusted is True
    assert interval.start_s == 0.3
    assert interval.end_s == 2.0


def test_build_trial_interval_accepts_frame_based_bounds(release_video: Path) -> None:
    video = load_trial_video(release_video)

    interval = build_trial_interval(video, start_frame=2, end_frame=20)

    assert interval.manually_adjusted is True
    assert interval.start_frame == 2
    assert interval.end_frame == 20
    assert interval.start_s == pytest.approx(2 / video.fps_real)
    assert interval.end_s == pytest.approx(20 / video.fps_real)


def test_build_trial_interval_rejects_both_representations_for_same_bound(
    release_video: Path,
) -> None:
    video = load_trial_video(release_video)

    with pytest.raises(TrialIntervalError):
        build_trial_interval(video, start_s=1.0, start_frame=10)


def test_build_trial_interval_rejects_end_before_start(release_video: Path) -> None:
    video = load_trial_video(release_video)

    with pytest.raises(TrialIntervalError):
        build_trial_interval(video, start_s=2.0, end_s=1.0)


def test_build_trial_interval_rejects_bounds_outside_video_duration(
    release_video: Path,
) -> None:
    video = load_trial_video(release_video)

    with pytest.raises(TrialIntervalError):
        build_trial_interval(video, end_s=video.duration_s + 10.0)


# --- RN05 — tempo zero ancorado no início do intervalo ---------------------


def test_seconds_from_trial_start_anchors_to_interval_start() -> None:
    interval = TrialInterval(
        start_s=12.0, end_s=312.0, start_frame=360, end_frame=9360, manually_adjusted=False
    )

    assert seconds_from_trial_start(12.0, interval) == 0.0
    assert seconds_from_trial_start(42.0, interval) == pytest.approx(30.0)


# --- RN02 — nada fora do intervalo -----------------------------------------


def test_is_within_interval_matches_cenario_3_bounds() -> None:
    interval = TrialInterval(
        start_s=12.0, end_s=312.0, start_frame=360, end_frame=9360, manually_adjusted=False
    )

    assert is_within_interval(11.999, interval) is False
    assert is_within_interval(12.0, interval) is True
    assert is_within_interval(200.0, interval) is True
    assert is_within_interval(312.0, interval) is True
    assert is_within_interval(312.001, interval) is False


def test_trimmed_frame_range_excludes_frames_outside_interval() -> None:
    interval = TrialInterval(
        start_s=1.0, end_s=2.0, start_frame=10, end_frame=20, manually_adjusted=False
    )

    frame_range = trimmed_frame_range(interval)

    assert list(frame_range) == list(range(10, 21))
    assert 9 not in frame_range
    assert 21 not in frame_range
