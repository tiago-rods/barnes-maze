from __future__ import annotations

import pytest

from barnes.db.export import ExportContext, TrialIdentity
from barnes.events.discovery import DiscoveryEvent
from barnes.geometry.holes import generate_holes
from barnes.report.probes_csv import (
    PROBE_DURATION_S,
    PROBES_CSV_ALL_COLUMNS,
    build_probes_row,
    missing_probes_row,
)

TARGET_HOLE = 0


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


def _context(straight_line_trajectory, *, discoveries) -> ExportContext:
    identity = TrialIdentity(
        trial_id=1,
        animal="A1",
        group_label="WT",
        day_number=1,
        trial_number_in_day=1,
        phase="probe",
    )
    return ExportContext(
        identity=identity,
        trajectory=straight_line_trajectory,
        geometry=_geometry(),
        rotation_deg=0.0,
        target_hole_number=TARGET_HOLE,
        discoveries=discoveries,
        entries=[],
        execucao_id=7,
    )


def test_build_probes_row_discovered(straight_line_trajectory):
    discoveries = [
        DiscoveryEvent(hole_number=TARGET_HOLE, quadro=30, t_s=3.0, distancia_cm=2.0, angulo_deg=5.0)
    ]
    context = _context(straight_line_trajectory, discoveries=discoveries)

    row = build_probes_row(context, probe_number=0)

    assert row["animal"] == "A1"
    assert row["group"] == "WT"
    assert row["probe"] == 0
    assert row["primary_latency"] == pytest.approx(3.0)
    assert row["primary_distance"] == pytest.approx(0.30)
    assert row["total_latency"] == pytest.approx(PROBE_DURATION_S)
    assert row["total_distance"] == pytest.approx(1.00)
    assert set(row.keys()) == set(PROBES_CSV_ALL_COLUMNS)


def test_build_probes_row_not_discovered(straight_line_trajectory):
    context = _context(straight_line_trajectory, discoveries=[])

    row = build_probes_row(context, probe_number=1)

    assert row["probe"] == 1
    assert row["primary_latency"] == pytest.approx(PROBE_DURATION_S)
    assert row["total_latency"] == pytest.approx(PROBE_DURATION_S)
    assert row["primary_latency"] == row["total_latency"]


def test_missing_probes_row_has_explicit_blanks():
    identity = TrialIdentity(
        trial_id=2,
        animal=None,
        group_label=None,
        day_number=1,
        trial_number_in_day=1,
        phase="probe",
    )

    row = missing_probes_row(identity, probe_number=0)

    assert row["animal"] == ""
    assert row["group"] == ""
    assert row["probe"] == 0
    for column in (
        "primary_latency",
        "primary_distance",
        "total_latency",
        "total_distance",
        "execucao_id",
        "path_distance",
        "mean_speed",
        "interpolated_fraction",
        "speed_time_base_approx",
        "pose_coverage",
    ):
        assert row[column] == ""
