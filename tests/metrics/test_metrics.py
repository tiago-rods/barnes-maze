"""Testes puros de src/barnes/metrics (US-02 RN03) — sem banco de dados."""

from __future__ import annotations

import pytest

from barnes.io.trim import interval_from_seconds
from barnes.metrics import distance_cm, process_trial, route_efficiency, speed_cm_s

# Intervalo útil largo o bastante para não cortar nada nos testes que não são de recorte.
WHOLE = interval_from_seconds(0.0, 1000.0, 25.0, manually_adjusted=False)


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
        interval=WHOLE,
        ideal_distance_px=80,
    )
    assert metrics["distance_cm"] == pytest.approx(10)
    assert metrics["mean_speed_cm_s"] == pytest.approx(2.5)
    assert metrics["duration_s"] == pytest.approx(4)
    assert metrics["sample_count"] == 3
    assert metrics["samples_outside_interval"] == 0
    assert metrics["ideal_distance_cm"] == pytest.approx(8)
    assert metrics["route_efficiency"] == pytest.approx(0.8)


def test_process_trial_without_ideal_distance_omits_route_efficiency():
    metrics = process_trial(
        0.1, [(10, 10), (40, 50)], [0, 2], frame_size=(640, 480), interval=WHOLE
    )
    assert "route_efficiency" not in metrics
    assert "ideal_distance_cm" not in metrics


def test_nothing_outside_the_useful_interval_enters_the_metrics():
    # US-03 Cenário 3: intervalo útil de 12 s a 312 s. Os trechos antes da
    # soltura (0 s → 12 s) e depois do fim (312 s → 400 s) são longos de
    # propósito: se entrassem, a distância mudaria muito.
    interval = interval_from_seconds(12.0, 312.0, 25.0, manually_adjusted=True)
    metrics = process_trial(
        0.1,
        [(500, 400), (10, 10), (40, 50), (70, 90), (600, 10)],
        [0.0, 12.0, 100.0, 312.0, 400.0],
        frame_size=(640, 480),
        interval=interval,
    )
    assert metrics["distance_cm"] == pytest.approx(10)  # só 10,10 → 40,50 → 70,90
    assert metrics["duration_s"] == pytest.approx(300)
    assert metrics["mean_speed_cm_s"] == pytest.approx(10 / 300)
    assert metrics["sample_count"] == 3
    assert metrics["samples_outside_interval"] == 2
    assert (metrics["interval_start_s"], metrics["interval_end_s"]) == (12.0, 312.0)


def test_trajectory_with_less_than_two_samples_inside_interval_is_rejected():
    interval = interval_from_seconds(12.0, 312.0, 25.0, manually_adjusted=False)
    with pytest.raises(ValueError, match="intervalo útil"):
        process_trial(
            0.1, [(10, 10), (40, 50), (70, 90)], [0.0, 5.0, 100.0],
            frame_size=(640, 480), interval=interval,
        )  # fmt: skip


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
        process_trial(0.1, points, times, frame_size=size, interval=WHOLE)


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
