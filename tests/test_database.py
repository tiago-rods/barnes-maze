"""Scale history, publication guards and atomic recalibration."""

import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from uuid import uuid4

import pytest

from barnes.db import CalibrationRepository, CalibrationRequiredError, StaleCalibrationError
from barnes.io.calibration import Segment, calculate_calibration


def scale(cm_per_px=0.1):
    return calculate_calibration(
        (
            Segment((10, 10), (110, 10), 100 * cm_per_px),
            Segment((20, 20), (20, 220), 200 * cm_per_px),
        )
    )


def save(repository, orientation="camera-day-1", cm_per_px=0.1, **kwargs):
    metadata = {
        "reference_video": "trial-1.mp4",
        "reference_frame": 3,
        "reference_size": (640, 480),
    }
    metadata.update(kwargs)
    return repository.save_calibration(orientation, scale(cm_per_px), **metadata)


@pytest.fixture
def repository(tmp_path):
    with CalibrationRepository(tmp_path / "barnes.sqlite3") as instance:
        yield instance


def test_calibration_persists_after_reopening_database(tmp_path):
    path = tmp_path / "scales.sqlite3"
    with CalibrationRepository(path) as repository:
        stored = save(repository)
        execution = repository.record_execution("trial-1", stored.id, {"distance_cm": 25.5})
    with CalibrationRepository(path) as reopened:
        assert reopened.require_calibration("camera-day-1") == stored
        assert reopened.get_calibration(stored.id) == stored
        assert reopened.get_execution(execution.id) == execution
        assert stored.cm_per_px == pytest.approx(0.1)
        assert stored.result.segments == scale().segments
        assert stored.reference_size == (640, 480)
        assert stored.version == 1


def test_sqlite_creates_missing_parent_directories(tmp_path):
    path = tmp_path / "nested" / "data" / "scales.sqlite3"
    with CalibrationRepository(path) as repository:
        assert save(repository).version == 1
    assert path.is_file()


def test_same_orientation_automatically_reuses_existing_scale(repository):
    stored = save(repository)
    for trial in ("trial-1", "trial-2"):
        selected = repository.require_calibration("camera-day-1")
        execution = repository.record_execution(trial, selected.id, {"distance_cm": 10})
        assert execution.calibration_id == stored.id
    assert len(repository.list_calibrations("camera-day-1")) == 1
    assert len(repository.list_executions()) == 2
    assert len(repository.list_executions("trial-1")) == 1


def test_missing_scale_has_actionable_message_and_cannot_publish(repository):
    assert repository.get_active_calibration("new-camera") is None
    with pytest.raises(CalibrationRequiredError, match="new-camera.*exige calibração"):
        repository.require_calibration("new-camera")
    with pytest.raises(CalibrationRequiredError):
        repository.record_execution("trial", "nonexistent-calibration", {"distance_cm": 10})
    assert repository.list_executions() == []


def test_recalibration_invalidates_results_without_rewriting_history(repository):
    old = save(repository)
    execution = repository.record_execution("trial-1", old.id, {"distance_cm": 25.5})
    new = save(repository, cm_per_px=0.2)
    historical = repository.get_execution(execution.id)
    assert historical.calibration_id == old.id
    assert historical.metrics == {"distance_cm": 25.5}
    assert historical.created_at == execution.created_at
    assert historical.is_valid is False
    assert historical.invalidated_at is not None
    assert repository.get_calibration(old.id) == old
    assert new.id != old.id
    assert new.version == 2
    assert repository.list_calibrations(old.orientation_id) == [old, new]
    assert repository.require_calibration(old.orientation_id) == new
    replacement = repository.record_execution("trial-1", new.id, {"distance_cm": 51})
    assert replacement.is_valid
    assert replacement.invalidated_at is None


def test_repeated_recalibration_retains_first_invalidation_time(repository):
    old = save(repository)
    execution = repository.record_execution("trial", old.id, {})
    save(repository, cm_per_px=0.2)
    first_invalidated = repository.get_execution(execution.id).invalidated_at
    save(repository, cm_per_px=0.3)
    assert repository.get_execution(execution.id).invalidated_at == first_invalidated


def test_orientation_scales_and_invalidation_are_isolated(repository):
    first = save(repository, "camera-A")
    second = save(repository, "camera-B", cm_per_px=0.2)
    first_run = repository.record_execution("A-trial", first.id, {"distance_cm": 1})
    second_run = repository.record_execution("B-trial", second.id, {"distance_cm": 2})
    save(repository, "camera-A", cm_per_px=0.3)
    assert not repository.get_execution(first_run.id).is_valid
    assert repository.get_execution(second_run.id) == second_run
    assert repository.require_calibration("camera-B") == second
    assert repository.list_calibrations("camera-B") == [second]


def test_publication_rejects_calibration_replaced_during_processing(repository):
    old = save(repository)
    save(repository, cm_per_px=0.2)
    with pytest.raises(StaleCalibrationError, match="Reprocesse"):
        repository.record_execution("trial", old.id, {"distance_cm": 10})
    assert repository.list_executions() == []


def test_failed_recalibration_rolls_back_new_scale_and_invalidation(repository):
    old = save(repository)
    execution = repository.record_execution("trial", old.id, {"distance_cm": 10})
    repository._connection.execute(
        "CREATE TRIGGER fail_invalidation BEFORE UPDATE ON executions "
        "BEGIN SELECT RAISE(ABORT, 'simulated database failure'); END"
    )
    with pytest.raises(sqlite3.IntegrityError, match="simulated database failure"):
        save(repository, cm_per_px=0.2)
    assert repository.require_calibration(old.orientation_id) == old
    assert repository.list_calibrations(old.orientation_id) == [old]
    assert repository.get_execution(execution.id) == execution
    repository._connection.execute("DROP TRIGGER fail_invalidation")
    assert save(repository, cm_per_px=0.2).version == 2


@pytest.mark.parametrize(
    "metadata",
    [
        {"reference_video": " "},
        {"reference_frame": -1},
        {"reference_frame": 1.5},
        {"reference_frame": True},
        {"reference_size": (0, 480)},
        {"reference_size": (640, False)},
        {"reference_size": (640.5, 480)},
        {"reference_size": (100, 100)},
        {"reference_size": (640,)},
    ],
)
def test_invalid_reference_metadata_is_not_persisted(repository, metadata):
    with pytest.raises(ValueError):
        save(repository, **metadata)
    assert repository.list_calibrations("camera-day-1") == []


@pytest.mark.parametrize("field", ["cm_per_px", "relative_disagreement", "angle_degrees"])
def test_inconsistent_calibration_result_cannot_be_persisted(repository, field):
    result = scale()
    malformed = replace(result, **{field: getattr(result, field) + 1})
    with pytest.raises(ValueError, match="não corresponde"):
        repository.save_calibration(
            "camera",
            malformed,
            reference_video="trial.mp4",
            reference_frame=0,
            reference_size=(640, 480),
        )


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), object()])
def test_nonfinite_or_non_json_metric_values_are_rejected(repository, bad):
    stored = save(repository)
    with pytest.raises(ValueError, match="finitos"):
        repository.record_execution("trial", stored.id, {"nested": {"velocity_cm_s": [bad]}})
    assert repository.list_executions() == []


def test_empty_identifiers_are_rejected(repository):
    with pytest.raises(ValueError):
        save(repository, " ")
    with pytest.raises(ValueError):
        repository.require_calibration("")
    stored = save(repository)
    with pytest.raises(ValueError):
        repository.record_execution("", stored.id, {})
    with pytest.raises(ValueError):
        repository.record_execution("trial", stored.id, {1: 10})


def test_sql_metacharacters_are_saved_as_data(repository):
    name = "camera'); DROP TABLE calibrations; --"
    stored = save(repository, name)
    assert repository.require_calibration(name) == stored
    assert save(repository, "another-camera").version == 1


def test_concurrent_recalibrations_receive_unique_versions(tmp_path):
    database = tmp_path / "concurrent.sqlite3"
    with CalibrationRepository(database) as first, CalibrationRepository(database) as second:
        save(first)
        gate = Barrier(2)

        def recalibrate(repository, value):
            gate.wait(timeout=10)
            return save(repository, cm_per_px=value)

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(recalibrate, first, 0.2),
                executor.submit(recalibrate, second, 0.3),
            ]
            results = [future.result(timeout=15) for future in futures]
        assert sorted(result.version for result in results) == [2, 3]
        assert len(first.list_calibrations("camera-day-1")) == 3


def test_concurrent_processing_and_recalibration_cannot_leave_valid_old_results(tmp_path):
    database = tmp_path / "publication.sqlite3"
    with CalibrationRepository(database) as first, CalibrationRepository(database) as second:
        old = save(first)
        gate = Barrier(2)

        def recalibrate():
            gate.wait(timeout=10)
            return save(first, cm_per_px=0.2)

        def publish():
            gate.wait(timeout=10)
            try:
                return second.record_execution("trial", old.id, {"distance_cm": 10})
            except StaleCalibrationError:
                return None

        with ThreadPoolExecutor(max_workers=2) as executor:
            changed = executor.submit(recalibrate)
            published = executor.submit(publish)
            assert changed.result(timeout=15).version == 2
            published.result(timeout=15)
        assert all(not execution.is_valid for execution in first.list_executions())


@pytest.mark.skipif(
    not os.environ.get("BARNES_TEST_POSTGRES_DSN"),
    reason="BARNES_TEST_POSTGRES_DSN não configurado; PostgreSQL externo opcional.",
)
def test_postgresql_persistence_and_recalibration():
    """Run against a dedicated test PostgreSQL; clean only this test's UUID rows."""
    orientation = "test-us02-" + str(uuid4())
    with CalibrationRepository(os.environ["BARNES_TEST_POSTGRES_DSN"]) as repository:
        try:
            old = save(repository, orientation)
            execution = repository.record_execution("trial", old.id, {"distance_cm": 10})
            new = save(repository, orientation, cm_per_px=0.2)
            assert new.version == 2
            assert repository.require_calibration(orientation) == new
            assert not repository.get_execution(execution.id).is_valid
            assert repository.get_execution(execution.id).calibration_id == old.id
            with pytest.raises(StaleCalibrationError):
                repository.record_execution("trial", old.id, {"distance_cm": 10})
        finally:
            with repository._transaction():
                repository._execute(
                    "DELETE FROM executions WHERE orientation_id = ?", (orientation,)
                )
                repository._execute(
                    "DELETE FROM calibrations WHERE orientation_id = ?", (orientation,)
                )
                repository._execute("DELETE FROM camera_orientations WHERE id = ?", (orientation,))
