import math

import pytest

from barnes.pose.regions import Region, RegionParams, classify_region


def test_center_point_is_centro(geometry, region_params) -> None:
    assert classify_region(160.0, 120.0, geometry, region_params) is Region.CENTRO


def test_point_on_hole_is_buraco(geometry, region_params) -> None:
    hole = geometry.holes[3]
    assert classify_region(hole.x_px, hole.y_px, geometry, region_params) is Region.BURACO


def test_point_within_margin_of_hole_is_buraco(geometry, region_params) -> None:
    hole = geometry.holes[0]  # ângulo 0°: buraco à direita do centro
    # raio 8 + margem de 1 raio = 16 px de alcance
    assert classify_region(hole.x_px - 15.0, hole.y_px, geometry, region_params) is Region.BURACO
    assert classify_region(hole.x_px - 17.0, hole.y_px, geometry, region_params) is Region.BORDA


def test_ring_between_holes_is_borda(geometry, region_params) -> None:
    # A 15°, a meio caminho entre os buracos de 0° e 30° (12 buracos), longe de ambos.
    x = 160.0 + 90.0 * math.cos(math.radians(15.0))
    y = 120.0 + 90.0 * math.sin(math.radians(15.0))
    assert classify_region(x, y, geometry, region_params) is Region.BORDA


def test_beyond_ring_is_borda(geometry, region_params) -> None:
    assert classify_region(160.0 + 105.0, 120.0 + 40.0, geometry, region_params) is Region.BORDA


def test_center_boundary_follows_fraction(geometry) -> None:
    params = RegionParams(center_radius_frac=0.5, hole_margin_radii=1.0)
    assert classify_region(160.0 + 45.0, 120.0, geometry, params) is Region.CENTRO
    assert classify_region(160.0 + 46.0, 120.0, geometry, params) is Region.BORDA


@pytest.mark.parametrize("frac", [0.0, 1.0, -0.2])
def test_invalid_center_fraction_rejected(frac) -> None:
    with pytest.raises(ValueError):
        RegionParams(center_radius_frac=frac, hole_margin_radii=1.0)


def test_negative_hole_margin_rejected() -> None:
    with pytest.raises(ValueError):
        RegionParams(center_radius_frac=0.5, hole_margin_radii=-1.0)
