from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from barnes.io.video import read_reference_frame


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


def test_reads_first_frame_without_seeking_and_releases(video_capture):
    path, capture, constructor = video_capture

    frame = read_reference_frame(path)

    assert frame is capture.read.return_value[1]
    constructor.assert_called_once_with(str(path))
    capture.set.assert_not_called()
    capture.release.assert_called_once()


def test_seeks_requested_frame_and_releases(video_capture):
    path, capture, _ = video_capture

    read_reference_frame(path, 20)

    capture.set.assert_called_once_with(cv2.CAP_PROP_POS_FRAMES, 20)
    capture.release.assert_called_once()


@pytest.mark.parametrize("index", [-1, True, 0.5, "0"])
def test_rejects_invalid_frame_index_before_opening(video_capture, index):
    path, _, constructor = video_capture
    with pytest.raises(ValueError, match="índice do quadro"):
        read_reference_frame(path, index)
    constructor.assert_not_called()


def test_missing_video_fails_before_opening(tmp_path, monkeypatch):
    constructor = Mock()
    monkeypatch.setattr(cv2, "VideoCapture", constructor)
    with pytest.raises(ValueError, match="não encontrado"):
        read_reference_frame(tmp_path / "missing.mp4")
    constructor.assert_not_called()


def test_unreadable_video_releases_capture(video_capture):
    path, capture, _ = video_capture
    capture.isOpened.return_value = False
    with pytest.raises(ValueError, match="abrir o vídeo"):
        read_reference_frame(path)
    capture.release.assert_called_once()


def test_failed_seek_does_not_return_another_frame(video_capture):
    path, capture, _ = video_capture
    capture.set.return_value = False
    with pytest.raises(ValueError, match="acessar o quadro 12"):
        read_reference_frame(path, 12)
    capture.read.assert_not_called()
    capture.release.assert_called_once()


@pytest.mark.parametrize(
    "read_result", [(False, None), (True, None), (True, np.zeros((0, 0, 3), np.uint8))]
)
def test_undecodable_frame_releases_capture(video_capture, read_result):
    path, capture, _ = video_capture
    capture.read.return_value = read_result
    with pytest.raises(ValueError, match="ler o quadro"):
        read_reference_frame(path)
    capture.release.assert_called_once()


def test_decoder_error_releases_capture(video_capture):
    path, capture, _ = video_capture
    capture.read.side_effect = cv2.error("invalid codec")
    with pytest.raises(ValueError, match="decodificar o vídeo"):
        read_reference_frame(path)
    capture.release.assert_called_once()
