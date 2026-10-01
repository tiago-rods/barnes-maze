import pytest

from barnes.db import CalibrationRepository, CalibrationRequiredError, StaleCalibrationError
from barnes.io.calibration import Segment, calibrate_orientation
from barnes.metrics import distance_cm, process_trial, route_efficiency, speed_cm_s


@pytest.fixture
def repository(tmp_path):
    with CalibrationRepository(tmp_path / "metrics.sqlite3") as repository:
        yield repository


def save(repository, scale=0.1, orientation="camera-A"):
    return calibrate_orientation(
        repository,
        orientation,
        [Segment((10, 10), (110, 10), scale * 100), Segment((20, 20), (20, 220), scale * 200)],
        reference_video="trial.mp4",
        reference_frame=0,
        reference_size=(640, 480),
    )


@pytest.mark.parametrize(
    "metric,args",
    [
        (distance_cm, (100,)),
        (speed_cm_s, (100, 2)),
        (route_efficiency, (50, 100)),
    ],
)
def test_every_metric_requires_calibration(repository, metric, args):
    with pytest.raises(CalibrationRequiredError, match="camera-A.*exige calibração"):
        metric(repository, "camera-A", *args)


def test_processing_without_scale_is_blocked_before_accessing_trajectory(repository):
    def unreadable():
        pytest.fail("Não deve ler a trajetória sem uma escala.")
        yield

    with pytest.raises(CalibrationRequiredError):
        process_trial(repository, "trial", "camera-A", unreadable(), [], frame_size=(640, 480))
    assert repository.list_executions() == []


def test_distance_speed_and_efficiency_with_persisted_scale(repository):
    save(repository)
    assert distance_cm(repository, "camera-A", 250) == pytest.approx(25)
    assert speed_cm_s(repository, "camera-A", 250, 5) == pytest.approx(5)
    assert route_efficiency(repository, "camera-A", 100, 250) == pytest.approx(0.4)
    assert route_efficiency(repository, "camera-A", 0, 0) is None


def test_processing_reuses_scale_and_reprocessing_preserves_history(repository):
    first_scale = save(repository)
    arguments = ([(10, 10), (40, 50), (70, 90)], [0, 2, 4])
    first = process_trial(repository, "trial-1", "camera-A", *arguments, frame_size=(640, 480))
    second = process_trial(repository, "trial-2", "camera-A", *arguments, frame_size=(640, 480))
    assert first.calibration_id == second.calibration_id == first_scale.id
    assert first.metrics["distance_cm"] == pytest.approx(10)
    assert first.metrics["mean_speed_cm_s"] == pytest.approx(2.5)
    new_scale = save(repository, 0.2)
    updated = process_trial(
        repository,
        "trial-1",
        "camera-A",
        *arguments,
        frame_size=(640, 480),
        ideal_distance_px=80,
    )
    assert updated.calibration_id == new_scale.id
    assert updated.metrics["distance_cm"] == pytest.approx(20)
    assert updated.metrics["route_efficiency"] == pytest.approx(0.8)
    assert repository.get_execution(first.id).metrics == first.metrics
    assert not repository.get_execution(first.id).is_valid
    assert not repository.get_execution(second.id).is_valid
    assert repository.get_execution(updated.id).is_valid


def test_other_camera_scale_is_not_used_as_a_fallback(repository):
    save(repository, orientation="camera-B")
    with pytest.raises(CalibrationRequiredError):
        distance_cm(repository, "camera-A", 100)


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
        ([(0, 0), (1, 1)], [0, 1], (320, 240)),
    ],
)
def test_invalid_trajectory_never_publishes_metrics(repository, points, times, size):
    save(repository)
    with pytest.raises(ValueError):
        process_trial(repository, "trial", "camera-A", points, times, frame_size=size)
    assert repository.list_executions() == []


def test_recalibration_during_processing_cannot_publish_stale_result(repository):
    save(repository)

    def trajectory():
        yield (10, 10)
        save(repository, 0.2)
        yield (110, 10)

    with pytest.raises(StaleCalibrationError):
        process_trial(repository, "trial", "camera-A", trajectory(), [0, 1], frame_size=(640, 480))
    assert repository.list_executions() == []


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
def test_invalid_metric_inputs_are_rejected(repository, metric, args):
    save(repository)
    with pytest.raises(ValueError):
        metric(repository, "camera-A", *args)
