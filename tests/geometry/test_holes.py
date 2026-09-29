import math

import pytest

from barnes.geometry.holes import generate_holes
from barnes.geometry.validation import GeometryValidationError


def test_generate_holes_equally_spaced() -> None:
    geometry = generate_holes(
        center_x_px=0.0,
        center_y_px=0.0,
        platform_radius_px=100.0,
        hole_count=8,
        start_angle_deg=0.0,
        target_hole_number=0,
        hole_radius_px=10.0,
    )
    angles = [hole.angle_deg for hole in geometry.holes]
    for i in range(len(angles) - 1):
        assert (angles[i + 1] - angles[i]) == pytest.approx(45.0)
    # volta ao início dando a volta completa
    assert (angles[0] + 360.0 - angles[-1]) == pytest.approx(45.0)


def test_generate_holes_target_hole_is_marked() -> None:
    geometry = generate_holes(
        center_x_px=0.0,
        center_y_px=0.0,
        platform_radius_px=100.0,
        hole_count=6,
        start_angle_deg=0.0,
        target_hole_number=3,
        hole_radius_px=10.0,
    )
    assert geometry.target_hole.hole_number == 3
    for hole in geometry.holes:
        assert hole.is_target == (hole.hole_number == 3)


def test_generate_holes_angles_normalized_to_0_360() -> None:
    for start_angle in (-30.0, 370.0):
        geometry = generate_holes(
            center_x_px=0.0,
            center_y_px=0.0,
            platform_radius_px=100.0,
            hole_count=5,
            start_angle_deg=start_angle,
            target_hole_number=0,
            hole_radius_px=10.0,
        )
        for hole in geometry.holes:
            assert 0.0 <= hole.angle_deg < 360.0


def test_generate_holes_positions_match_trigonometry() -> None:
    geometry = generate_holes(
        center_x_px=50.0,
        center_y_px=50.0,
        platform_radius_px=100.0,
        hole_count=4,
        start_angle_deg=0.0,
        target_hole_number=0,
        hole_radius_px=10.0,
    )
    # hole 0: angulo 0 -> eixo +x
    assert geometry.holes[0].x_px == pytest.approx(150.0)
    assert geometry.holes[0].y_px == pytest.approx(50.0)
    # hole 1: 90 graus -> eixo +y (sentido horario na tela, y para baixo)
    assert geometry.holes[1].x_px == pytest.approx(50.0)
    assert geometry.holes[1].y_px == pytest.approx(150.0)
    # hole 2: 180 graus -> eixo -x
    assert geometry.holes[2].x_px == pytest.approx(-50.0)
    assert geometry.holes[2].y_px == pytest.approx(50.0)
    # hole 3: 270 graus -> eixo -y
    assert geometry.holes[3].x_px == pytest.approx(50.0)
    assert geometry.holes[3].y_px == pytest.approx(-50.0)


def test_generate_holes_propagates_validation_error() -> None:
    with pytest.raises(GeometryValidationError) as exc_info:
        generate_holes(
            center_x_px=0.0,
            center_y_px=0.0,
            platform_radius_px=100.0,
            hole_count=2,
            start_angle_deg=0.0,
            target_hole_number=0,
            hole_radius_px=10.0,
        )
    assert exc_info.value.field == "hole_count"


def test_hole_proximity_zone_is_circle_around_hole() -> None:
    geometry = generate_holes(
        center_x_px=0.0,
        center_y_px=0.0,
        platform_radius_px=100.0,
        hole_count=4,
        start_angle_deg=0.0,
        target_hole_number=0,
        hole_radius_px=10.0,
    )
    hole = geometry.holes[0]
    zone = hole.proximity_zone()
    assert zone.centroid.x == pytest.approx(hole.x_px, abs=1e-6)
    assert zone.centroid.y == pytest.approx(hole.y_px, abs=1e-6)
    assert zone.area == pytest.approx(math.pi * hole.radius_px**2, rel=0.01)


def test_hole_proximity_zone_margin() -> None:
    geometry = generate_holes(
        center_x_px=0.0,
        center_y_px=0.0,
        platform_radius_px=100.0,
        hole_count=4,
        start_angle_deg=0.0,
        target_hole_number=0,
        hole_radius_px=10.0,
    )
    hole = geometry.holes[0]
    assert hole.proximity_zone(margin_px=5.0).area > hole.proximity_zone().area
