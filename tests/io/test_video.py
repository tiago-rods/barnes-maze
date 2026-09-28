"""Testes de src/barnes/io/video.py (US-01)."""

from __future__ import annotations

import pytest

from barnes.io.video import (
    VideoLoadError,
    is_fps_variable,
    load_trial_video,
    real_fps_from_timestamps,
)


def test_real_fps_from_timestamps_constant_interval() -> None:
    timestamps = [i * 100.0 for i in range(10)]  # 100ms entre quadros = 10 fps
    assert real_fps_from_timestamps(timestamps) == pytest.approx(10.0)


def test_real_fps_from_timestamps_requires_at_least_two_points() -> None:
    with pytest.raises(ValueError):
        real_fps_from_timestamps([0.0])


def test_is_fps_variable_false_for_constant_interval() -> None:
    timestamps = [i * 33.33 for i in range(30)]
    assert is_fps_variable(timestamps) is False


def test_is_fps_variable_true_for_irregular_interval() -> None:
    timestamps = [0.0, 33.33, 66.66, 200.0, 233.33, 266.66]  # salto de ~130ms no meio
    assert is_fps_variable(timestamps) is True


def test_load_trial_video_happy_path(make_mp4) -> None:
    video_path = make_mp4(frame_count=15, fps=15.0)

    video = load_trial_video(video_path)

    assert video.width == 64
    assert video.height == 48
    assert video.frame_count == 15
    assert video.fps_is_variable is False
    assert video.fps_real == pytest.approx(15.0, rel=0.2)
    assert len(video.content_hash) == 64  # sha256 em hexadecimal


def test_load_trial_video_missing_file(tmp_path) -> None:
    with pytest.raises(VideoLoadError):
        load_trial_video(tmp_path / "nao_existe.mp4")


def test_load_trial_video_unsupported_extension(tmp_path) -> None:
    fake = tmp_path / "video.avi"
    fake.write_bytes(b"nao e um video de verdade")

    with pytest.raises(VideoLoadError):
        load_trial_video(fake)


def test_load_trial_video_corrupted_file(tmp_path) -> None:
    fake = tmp_path / "corrupted.mp4"
    fake.write_bytes(b"nao e um mp4 de verdade" * 100)

    with pytest.raises(VideoLoadError):
        load_trial_video(fake)
