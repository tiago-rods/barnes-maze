"""US-02: independent accuracy on a synthetic image and pure calibration API."""

from math import nan

import cv2
import numpy as np
import pytest

from barnes.db import CalibrationRepository
from barnes.io.calibration import (
    CalibrationError,
    Segment,
    calculate_calibration,
    calibrate_orientation,
    verify_distance,
)


def reference_calibration():
    return calculate_calibration([Segment((0, 0), (200, 0), 20), Segment((0, 0), (0, 300), 30)])


@pytest.mark.parametrize("click_error_px", [0, 1, -1])
def test_independent_distance_error_below_three_percent_in_synthetic_image(click_error_px):
    # Known ground truth: 10 pixels/cm. The blue diagonal is not used to fit scale.
    image = np.zeros((600, 800, 3), dtype=np.uint8)
    markers = [
        ((0, 0, 255), [(60, 60), (260, 60)]),  # 20 cm horizontal
        ((0, 255, 0), [(60, 150), (60, 450)]),  # 30 cm vertical
        ((255, 0, 0), [(400, 200), (550, 400)]),  # 25 cm diagonal (150, 200)
    ]
    for color, endpoints in markers:
        for point in endpoints:
            cv2.circle(image, point, 4, color, -1)

    def detect_points(color):
        mask = cv2.inRange(image, np.array(color), np.array(color))
        count, _, _, centroids = cv2.connectedComponentsWithStats(mask)
        assert count == 3  # Background + two reference markers.
        return [tuple(point) for point in centroids[1:]]

    first = detect_points((0, 0, 255))
    second = detect_points((0, 255, 0))
    first[1] = (first[1][0] + click_error_px, first[1][1])
    calibration = calculate_calibration([Segment(*first, 20), Segment(*second, 30)])
    independent = Segment(*detect_points((255, 0, 0)), 25)
    result = verify_distance(calibration, independent)
    assert result.accepted
    assert result.relative_error < 0.03
    assert result.measured_cm == pytest.approx(25, rel=0.003)


def test_average_of_two_distinct_known_lengths_and_directions():
    result = calculate_calibration(
        [Segment((0, 0), (100, 0), 10), Segment((50, 50), (50, 250), 20.2)]
    )
    assert result.cm_per_px == pytest.approx(0.1005)
    assert result.relative_disagreement == pytest.approx(0.001 / 0.1005)
    assert result.angle_degrees == pytest.approx(90)


@pytest.mark.parametrize("length", [0, -1, nan, float("inf"), True, "bad"])
def test_invalid_real_lengths_are_rejected(length):
    with pytest.raises(CalibrationError):
        Segment((0, 0), (10, 0), length)


@pytest.mark.parametrize("point", [(nan, 0), (-1, 0), (0,), (0, 1, 2), (True, 1), None])
def test_invalid_points_are_rejected(point):
    with pytest.raises(CalibrationError):
        Segment(point, (20, 20), 10)


def test_zero_length_segment_is_rejected():
    with pytest.raises(CalibrationError):
        Segment((1, 1), (1, 1), 10)


@pytest.mark.parametrize("count", [0, 1, 3])
def test_exactly_two_segments_required(count):
    with pytest.raises(CalibrationError, match="exatamente dois"):
        calculate_calibration([Segment((0, 0), (20, 0), 2)] * count)


@pytest.mark.parametrize("second", [((0, 10), (200, 10)), ((200, 10), (0, 10))])
def test_parallel_directions_cannot_detect_perspective(second):
    with pytest.raises(CalibrationError, match="direções diferentes"):
        calculate_calibration([Segment((0, 0), (200, 0), 20), Segment(*second, 20)])


def test_conflicting_scales_detect_perspective_instead_of_averaging_it_away():
    with pytest.raises(CalibrationError, match="perspectiva"):
        calculate_calibration([Segment((0, 0), (200, 0), 20), Segment((0, 0), (0, 200), 25)])


def test_exact_three_percent_inter_segment_disagreement_is_rejected():
    with pytest.raises(CalibrationError, match="divergem"):
        calculate_calibration([Segment((0, 0), (100, 0), 9.85), Segment((0, 0), (0, 100), 10.15)])


@pytest.mark.parametrize("pixels,accepted", [(102.99, True), (103, False), (104, False)])
def test_independent_error_limit_is_strict(pixels, accepted):
    result = verify_distance(reference_calibration(), Segment((300, 50), (300 + pixels, 50), 10))
    assert result.accepted is accepted


@pytest.mark.parametrize("reverse", [False, True])
def test_validation_rejects_reusing_a_calibration_segment(reverse):
    known = reference_calibration()
    used = known.segments[0]
    segment = Segment(used.end, used.start, used.length_cm) if reverse else used
    with pytest.raises(CalibrationError, match="independente"):
        verify_distance(known, segment)


def test_callable_calibration_saves_without_a_window(tmp_path, monkeypatch):
    def unexpected_window(*args, **kwargs):
        pytest.fail("A função de calibração não pode abrir uma janela.")

    monkeypatch.setattr(cv2, "namedWindow", unexpected_window)
    with CalibrationRepository(tmp_path / "scale.sqlite3") as repository:
        saved = calibrate_orientation(
            repository,
            "camera-A",
            reference_calibration().segments,
            reference_video="trial.mp4",
            reference_frame=0,
            reference_size=(640, 480),
        )
        assert saved.cm_per_px == pytest.approx(0.1)
        assert repository.require_calibration("camera-A").id == saved.id
