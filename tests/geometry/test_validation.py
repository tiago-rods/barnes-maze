import pytest

from barnes.geometry.validation import GeometryValidationError, validate_parameters


def test_validate_parameters_accepts_valid_input() -> None:
    validate_parameters(hole_count=20, platform_radius_px=100.0, target_hole_number=0)


def test_validate_parameters_rejects_hole_count_le_2() -> None:
    with pytest.raises(GeometryValidationError) as exc_info:
        validate_parameters(hole_count=2, platform_radius_px=100.0, target_hole_number=0)
    assert exc_info.value.field == "hole_count"


def test_validate_parameters_rejects_non_positive_radius() -> None:
    for radius in (0.0, -10.0):
        with pytest.raises(GeometryValidationError) as exc_info:
            validate_parameters(hole_count=20, platform_radius_px=radius, target_hole_number=0)
        assert exc_info.value.field == "platform_radius_px"


def test_validate_parameters_rejects_target_out_of_range() -> None:
    with pytest.raises(GeometryValidationError) as exc_info:
        validate_parameters(hole_count=8, platform_radius_px=100.0, target_hole_number=8)
    assert exc_info.value.field == "target_hole_number"

    with pytest.raises(GeometryValidationError) as exc_info:
        validate_parameters(hole_count=8, platform_radius_px=100.0, target_hole_number=-1)
    assert exc_info.value.field == "target_hole_number"
