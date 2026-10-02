"""Testes de src/barnes/io/video.py (US-01)."""

from __future__ import annotations

from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from barnes.io.video import (
    VideoLoadError,
    is_fps_variable,
    load_trial_video,
    read_frame,
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


def test_is_fps_variable_false_for_bframe_alternating_pattern() -> None:
    # Vídeo real (câmera do LNBio, codec com B-frames) mostrou POS_MSEC alternando
    # ~32ms/~48ms (media 40ms = 25fps) sem que o fps seja de fato variável —
    # isso não pode voltar a disparar falso positivo.
    timestamps = [0.0]
    for i in range(40):
        timestamps.append(timestamps[-1] + (32.0 if i % 2 == 0 else 48.0))
    assert is_fps_variable(timestamps) is False


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


# --- read_frame com proteções vindas da US-02 (quadro de referência) ----------


@pytest.fixture
def video_capture(tmp_path, monkeypatch):
    path = tmp_path / "reference.mp4"
    path.touch()
    capture = Mock()
    capture.isOpened.return_value = True
    capture.set.return_value = True
    capture.read.return_value = (True, np.zeros((100, 200, 3), dtype=np.uint8))
    constructor = Mock(return_value=capture)
    monkeypatch.setattr(cv2, "VideoCapture", constructor)
    return path, capture, constructor


def test_read_frame_first_frame_without_seeking_and_releases(video_capture) -> None:
    path, capture, constructor = video_capture

    frame = read_frame(path)

    assert frame is capture.read.return_value[1]
    constructor.assert_called_once_with(str(path))
    capture.set.assert_not_called()
    capture.release.assert_called_once()


def test_read_frame_seeks_requested_frame_and_releases(video_capture) -> None:
    path, capture, _ = video_capture

    read_frame(path, 20)

    capture.set.assert_called_once_with(cv2.CAP_PROP_POS_FRAMES, 20)
    capture.release.assert_called_once()


@pytest.mark.parametrize("index", [-1, True, 0.5, "0"])
def test_read_frame_rejects_invalid_index_before_opening(video_capture, index) -> None:
    path, _, constructor = video_capture
    with pytest.raises(VideoLoadError, match="índice do quadro"):
        read_frame(path, index)
    constructor.assert_not_called()


def test_read_frame_missing_video_fails_before_opening(tmp_path, monkeypatch) -> None:
    constructor = Mock()
    monkeypatch.setattr(cv2, "VideoCapture", constructor)
    with pytest.raises(VideoLoadError, match="não encontrado"):
        read_frame(tmp_path / "missing.mp4")
    constructor.assert_not_called()


def test_read_frame_unreadable_video_releases_capture(video_capture) -> None:
    path, capture, _ = video_capture
    capture.isOpened.return_value = False
    with pytest.raises(VideoLoadError, match="abrir o vídeo"):
        read_frame(path)
    capture.release.assert_called_once()


def test_read_frame_failed_seek_does_not_return_another_frame(video_capture) -> None:
    path, capture, _ = video_capture
    capture.set.return_value = False
    with pytest.raises(VideoLoadError, match="acessar o quadro 12"):
        read_frame(path, 12)
    capture.read.assert_not_called()
    capture.release.assert_called_once()


@pytest.mark.parametrize(
    "read_result", [(False, None), (True, None), (True, np.zeros((0, 0, 3), np.uint8))]
)
def test_read_frame_undecodable_frame_releases_capture(video_capture, read_result) -> None:
    path, capture, _ = video_capture
    capture.read.return_value = read_result
    with pytest.raises(VideoLoadError, match="ler o quadro"):
        read_frame(path)
    capture.release.assert_called_once()


def test_read_frame_decoder_error_releases_capture(video_capture) -> None:
    path, capture, _ = video_capture
    capture.read.side_effect = cv2.error("invalid codec")
    with pytest.raises(VideoLoadError, match="decodificar o vídeo"):
        read_frame(path)
    capture.release.assert_called_once()
