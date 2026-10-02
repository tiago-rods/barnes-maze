"""Exercise the actual point collector without opening a desktop window."""

from collections import deque

import cv2
import numpy as np
import pytest

from barnes.io.calibration_ui import CalibrationCancelled, collect_segments


class FakeWindow:
    def __init__(self, monkeypatch, actions):
        self.actions = deque(actions)
        self.visible = 1
        self.closed = False
        self.callback = None
        self.window_flag = None
        self.shapes = []
        self.property_error = False
        monkeypatch.setattr(cv2, "namedWindow", self.create)
        monkeypatch.setattr(cv2, "setMouseCallback", self.set_callback)
        monkeypatch.setattr(cv2, "imshow", self.show)
        monkeypatch.setattr(cv2, "waitKey", self.wait)
        monkeypatch.setattr(cv2, "getWindowProperty", self.get_property)
        monkeypatch.setattr(cv2, "destroyWindow", self.destroy)

    def create(self, name, flag):
        self.window_flag = flag

    def set_callback(self, name, callback):
        self.callback = callback

    def show(self, name, image):
        self.shapes.append(image.shape)

    def wait(self, delay):
        assert self.actions, "Point collection did not finish after the scripted actions"
        action = self.actions.popleft()
        if isinstance(action, int):
            return action
        if action[0] in ("left", "right"):
            event = cv2.EVENT_LBUTTONDOWN if action[0] == "left" else cv2.EVENT_RBUTTONDOWN
            self.callback(event, action[1], action[2], 0, None)
        elif action[0] == "close":
            self.visible = 0
        elif action[0] == "property_error":
            self.property_error = True
        return -1

    def get_property(self, name, prop):
        if self.property_error:
            raise cv2.error("window already closed")
        return self.visible

    def destroy(self, name):
        self.closed = True


def test_collects_two_segments_only_after_all_four_points(monkeypatch):
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    original = frame.copy()
    window = FakeWindow(
        monkeypatch,
        [
            13,
            ("left", 10, 20),
            ("left", 60, 20),
            13,
            ("left", 20, 30),
            ("left", 20, 80),
            ("left", 50, 50),
            13,
        ],
    )

    segments = collect_segments(frame)

    assert segments == (((10.0, 20.0), (60.0, 20.0)), ((20.0, 30.0), (20.0, 80.0)))
    assert window.window_flag == cv2.WINDOW_AUTOSIZE
    assert window.closed
    np.testing.assert_array_equal(frame, original)


def test_preview_coordinates_are_mapped_to_original_resolution(monkeypatch):
    window = FakeWindow(monkeypatch, [("left", 100, 120), ("left", 500, 600), 13])
    frame = np.zeros((1600, 2560, 3), dtype=np.uint8)

    segments = collect_segments(frame, segment_count=1)

    assert segments == (((200.0, 240.0), (1000.0, 1200.0)),)
    assert window.shapes[0] == (800, 1280, 3)


def test_resize_uses_single_ratio_consistently_on_both_axes(monkeypatch):
    """A 2001x901 frame rounds to height=576 under the width-constrained ratio.

    Recomputing x_scale/y_scale independently from the *rounded* resized
    dimensions (2001/1280 vs. 901/576) gives each axis a slightly different
    factor. Both clicked coordinates must scale back by the same factor
    (1 / ratio), not by two axis-specific ones.
    """
    FakeWindow(monkeypatch, [("left", 100, 100), ("left", 300, 200), 13])
    frame = np.zeros((901, 2001, 3), dtype=np.uint8)

    segments = collect_segments(frame, segment_count=1)

    scale = 2001 / 1280
    assert segments[0][0] == pytest.approx((100 * scale, 100 * scale))
    assert segments[0][1] == pytest.approx((300 * scale, 200 * scale))


def test_ignore_out_of_bounds_and_support_undo_and_reset(monkeypatch):
    FakeWindow(
        monkeypatch,
        [
            ("left", -1, 10),
            ("left", 100, 10),
            ("left", 10, 100),
            ("right", 0, 0),
            ("left", 10, 10),
            ("right", 0, 0),
            ("left", 20, 20),
            8,
            ("left", 30, 30),
            ord("r"),
            ("left", 40, 40),
            ("left", 80, 80),
            13,
        ],
    )

    assert collect_segments(np.zeros((100, 100, 3), np.uint8), segment_count=1) == (
        ((40.0, 40.0), (80.0, 80.0)),
    )


@pytest.mark.parametrize("action", [27, ord("x"), ("close",), ("property_error",)])
def test_cancellation_releases_window(monkeypatch, action):
    window = FakeWindow(monkeypatch, [("left", 10, 10), action])

    with pytest.raises(CalibrationCancelled, match="nenhum dado foi salvo"):
        collect_segments(np.zeros((100, 100, 3), np.uint8))

    assert window.closed


def test_gui_failure_is_actionable_and_releases_window(monkeypatch):
    window = FakeWindow(monkeypatch, [])

    def fail_show(*args):
        raise cv2.error("GUI unavailable")

    monkeypatch.setattr(cv2, "imshow", fail_show)
    with pytest.raises(RuntimeError, match="ambiente gráfico"):
        collect_segments(np.zeros((100, 100, 3), np.uint8))

    assert window.closed


@pytest.mark.parametrize("segment_count", [True, 0, -1, 1.5])
def test_invalid_segment_count(segment_count):
    with pytest.raises(ValueError, match="inteiro positivo"):
        collect_segments(np.zeros((100, 100, 3), np.uint8), segment_count=segment_count)


@pytest.mark.parametrize(
    "frame", [None, np.zeros((0, 1, 3)), np.zeros((4, 4)), np.zeros((4, 4, 2), np.uint8)]
)
def test_invalid_frame(frame):
    with pytest.raises(ValueError, match="quadro de referência"):
        collect_segments(frame)
