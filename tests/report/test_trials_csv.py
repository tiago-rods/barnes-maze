from __future__ import annotations

import pytest

from barnes.db.export import ExportContext, TrialIdentity
from barnes.events.discovery import DiscoveryEvent
from barnes.events.entry import EntryEvent
from barnes.geometry.holes import generate_holes
from barnes.report.trials_csv import TRIALS_CSV_ALL_COLUMNS, build_trials_row, missing_trials_row

TARGET_HOLE = 0
OTHER_HOLE = 5


def _geometry():
    return generate_holes(
        center_x_px=0,
        center_y_px=0,
        platform_radius_px=50,
        hole_count=8,
        start_angle_deg=0,
        target_hole_number=TARGET_HOLE,
        hole_radius_px=5,
    )


def _context(
    straight_line_trajectory,
    *,
    entries,
    search_strategy=None,
    entropy_bits=None,
) -> ExportContext:
    identity = TrialIdentity(
        trial_id=1,
        animal="A1",
        group_label="WT",
        day_number=2,
        trial_number_in_day=3,
        phase="acquisition",
    )
    discoveries = [
        DiscoveryEvent(hole_number=TARGET_HOLE, quadro=30, t_s=3.0, distancia_cm=2.0, angulo_deg=5.0),
        DiscoveryEvent(hole_number=OTHER_HOLE, quadro=10, t_s=1.0, distancia_cm=2.5, angulo_deg=4.0),
    ]
    return ExportContext(
        identity=identity,
        trajectory=straight_line_trajectory,
        geometry=_geometry(),
        cm_per_px=1.0,
        rotation_deg=0.0,
        target_hole_number=TARGET_HOLE,
        discoveries=discoveries,
        entries=entries,
        execucao_id=42,
        search_strategy=search_strategy,
        entropy_bits=entropy_bits,
    )


def test_build_trials_row_observed(straight_line_trajectory):
    entries = [
        EntryEvent(
            hole_number=TARGET_HOLE,
            quadro=35,
            t_s=3.5,
            confirmed_at_s=3.7,
            delta_latency=0.5,
            delta_distance_cm=5.0,
            total_latency=3.5,
            total_distance_cm=35.0,
            discovery_quadro=30,
            discovery_t_s=3.0,
            dwell_s=1.0,
            dwell_interpolado=False,
        ),
        EntryEvent(
            hole_number=OTHER_HOLE,
            quadro=12,
            t_s=1.2,
            confirmed_at_s=1.4,
            delta_latency=0.2,
            delta_distance_cm=2.0,
            total_latency=None,
            total_distance_cm=None,
            discovery_quadro=10,
            discovery_t_s=1.0,
            dwell_s=0.4,
            dwell_interpolado=False,
        ),
    ]
    context = _context(
        straight_line_trajectory, entries=entries, search_strategy="spatial", entropy_bits=1.5
    )

    row = build_trials_row(context, tempo_limite_s=5.0)

    assert row["animal"] == "A1"
    assert row["group"] == "WT"
    assert row["day"] == 2
    assert row["trial"] == 3
    assert row["primary_latency"] == pytest.approx(3.0)
    assert row["primary_distance"] == pytest.approx(0.30)
    assert row["primary_event"] == 1
    assert row["delta_latency"] == pytest.approx(0.5)
    assert row["delta_distance"] == pytest.approx(0.05)
    assert row["total_latency"] == pytest.approx(3.5)
    assert row["total_distance"] == pytest.approx(0.35)
    assert row["total_event"] == 1
    assert row["execucao_id"] == 42
    assert row["path_distance"] == pytest.approx(1.00)
    assert row["mean_speed"] == pytest.approx(0.10)
    assert row["interpolated_fraction"] == pytest.approx(0.0)
    assert row["speed_time_base_approx"] is False
    assert row["pose_coverage"] == pytest.approx(1.0)
    assert row["search_strategy"] == "spatial"
    assert row["entropy_bits"] == pytest.approx(1.5)
    assert row["primary_route_efficiency"] == pytest.approx(1.0)
    assert row["total_route_efficiency"] == pytest.approx(1.0)
    assert set(row.keys()) == set(TRIALS_CSV_ALL_COLUMNS)


def test_build_trials_row_without_strategy_classification(straight_line_trajectory):
    """Um trial que ainda não passou por `barnes strategy classify` (RN04): ausente, não erro."""
    context = _context(straight_line_trajectory, entries=[])

    row = build_trials_row(context, tempo_limite_s=5.0)

    assert row["search_strategy"] == ""
    assert row["entropy_bits"] == ""


def test_build_trials_row_censored_by_time_limit(straight_line_trajectory):
    entries = [
        EntryEvent(
            hole_number=TARGET_HOLE,
            quadro=35,
            t_s=3.5,
            confirmed_at_s=3.7,
            delta_latency=0.5,
            delta_distance_cm=5.0,
            total_latency=3.5,
            total_distance_cm=35.0,
            discovery_quadro=30,
            discovery_t_s=3.0,
            dwell_s=1.0,
            dwell_interpolado=False,
        )
    ]
    context = _context(straight_line_trajectory, entries=entries)

    row = build_trials_row(context, tempo_limite_s=2.0)

    assert row["primary_event"] == 0
    assert row["primary_latency"] == pytest.approx(2.0)
    assert row["primary_distance"] == pytest.approx(0.20)
    assert row["total_event"] == 0
    assert row["total_latency"] == pytest.approx(2.0)
    assert row["total_distance"] == pytest.approx(0.20)
    assert row["delta_latency"] == pytest.approx(0.5)
    assert row["delta_distance"] == pytest.approx(0.05)


def test_build_trials_row_target_never_entered(straight_line_trajectory):
    context = _context(straight_line_trajectory, entries=[])

    row = build_trials_row(context, tempo_limite_s=5.0)

    assert row["primary_event"] == 1
    assert row["primary_latency"] == pytest.approx(3.0)
    assert row["total_event"] == 0
    assert row["total_latency"] == pytest.approx(5.0)
    assert row["delta_latency"] == ""
    assert row["delta_distance"] == ""


def test_missing_trials_row_has_explicit_blanks():
    identity = TrialIdentity(
        trial_id=9,
        animal="A9",
        group_label=None,
        day_number=1,
        trial_number_in_day=1,
        phase="acquisition",
    )

    row = missing_trials_row(identity)

    assert row["animal"] == "A9"
    assert row["group"] == ""
    assert row["day"] == 1
    assert row["trial"] == 1
    for column in (
        "primary_latency",
        "primary_distance",
        "primary_event",
        "delta_latency",
        "delta_distance",
        "total_latency",
        "total_distance",
        "total_event",
        "execucao_id",
        "path_distance",
        "mean_speed",
        "interpolated_fraction",
        "speed_time_base_approx",
        "pose_coverage",
        "search_strategy",
        "entropy_bits",
        "primary_route_efficiency",
        "total_route_efficiency",
    ):
        assert row[column] == ""
    assert set(row.keys()) == set(TRIALS_CSV_ALL_COLUMNS)
