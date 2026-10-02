"""Testes puros de src/barnes/metrics (US-02 RN03) — sem banco de dados."""

from __future__ import annotations

import pytest

from barnes.metrics import distance_cm, process_trial, route_efficiency, speed_cm_s


def test_distance_speed_and_efficiency():
    assert distance_cm(0.1, 250) == pytest.approx(25)
    assert speed_cm_s(0.1, 250, 5) == pytest.approx(5)
    assert route_efficiency(0.1, 100, 250) == pytest.approx(0.4)
    assert route_efficiency(0.1, 0, 0) is None


def test_process_trial_computes_distance_speed_and_efficiency():
    metrics = process_trial(
        0.1,
        [(10, 10), (40, 50), (70, 90)],
        [0, 2, 4],
        frame_size=(640, 480),
        ideal_distance_px=80,
    )
    assert metrics["distance_cm"] == pytest.approx(10)
    assert metrics["mean_speed_cm_s"] == pytest.approx(2.5)
    assert metrics["duration_s"] == pytest.approx(4)
    assert metrics["sample_count"] == 3
    assert metrics["ideal_distance_cm"] == pytest.approx(8)
    assert metrics["route_efficiency"] == pytest.approx(0.8)


def test_process_trial_without_ideal_distance_omits_route_efficiency():
    metrics = process_trial(0.1, [(10, 10), (40, 50)], [0, 2], frame_size=(640, 480))
    assert "route_efficiency" not in metrics
    assert "ideal_distance_cm" not in metrics


@pytest.mark.parametrize(
    "points,times,size",
    [
        ([(0, 0)], [0], (640, 480)),
        ([(0, 0), (1, 1)], [0], (640, 480)),
        ([(0, 0), (1, 1)], [1, 1], (640, 480)),
        ([(0, 0), (1, 1)], [2, 1], (640, 480)),
        ([(0, 0), (1, 1)], [0, float("nan")], (640, 480)),
        ([(0, 0), (float("nan"), 1)], [0, 1], (640, 480)),
        ([(0, 0), (640, 1)], [0, 1], (640, 480)),
    ],
)
def test_invalid_trajectory_is_rejected(points, times, size):
    with pytest.raises(ValueError):
        process_trial(0.1, points, times, frame_size=size)


@pytest.mark.parametrize(
    "metric,args",
    [
        (distance_cm, (-1,)),
        (distance_cm, (float("nan"),)),
        (speed_cm_s, (100, 0)),
        (speed_cm_s, (100, float("inf"))),
        (route_efficiency, (200, 100)),
    ],
)
def test_invalid_metric_inputs_are_rejected(metric, args):
    with pytest.raises(ValueError):
        metric(0.1, *args)
