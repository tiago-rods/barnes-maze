import pytest

from barnes.geometry.holes import generate_holes
from barnes.geometry.reference_frame import (
    MissingRotationError,
    ReferenceFrame,
    hole_to_room_angle,
    require_rotations,
    room_angle_to_hole,
    target_hole_for_trial,
    target_room_angle,
)


def _geometry(
    *,
    hole_count: int = 20,
    start_angle_deg: float = 0.0,
    target_hole_number: int = 0,
    center_x_px: float = 320.0,
    center_y_px: float = 240.0,
):
    return generate_holes(
        center_x_px=center_x_px,
        center_y_px=center_y_px,
        platform_radius_px=200.0,
        hole_count=hole_count,
        start_angle_deg=start_angle_deg,
        target_hole_number=target_hole_number,
        hole_radius_px=10.0,
    )


@pytest.mark.parametrize("hole_count", [3, 8, 20])
@pytest.mark.parametrize("rotation_deg", [0.0, 18.0, 90.0, 137.5, 359.0])
@pytest.mark.parametrize("start_angle_deg", [0.0, 73.0, 350.0])
def test_roundtrip_hole_room_hole_for_all_holes(hole_count, rotation_deg, start_angle_deg) -> None:
    # Cenário 2: índice -> sala -> índice recupera o original, para todos os N buracos.
    geometry = _geometry(hole_count=hole_count, start_angle_deg=start_angle_deg)
    for hole in geometry.holes:
        room = hole_to_room_angle(geometry, hole.hole_number, rotation_deg=rotation_deg)
        assert 0.0 <= room < 360.0
        assert room_angle_to_hole(geometry, room, rotation_deg=rotation_deg) == hole.hole_number


@pytest.mark.parametrize("hole_count", [3, 8, 20])
def test_without_rotation_room_angle_is_hole_index_times_step(hole_count) -> None:
    # B4 (LNBio não rotaciona): sala(k) = k * 360/N, independente da câmera.
    geometry = _geometry(hole_count=hole_count, start_angle_deg=41.0)
    step = 360.0 / hole_count
    for hole in geometry.holes:
        room = hole_to_room_angle(geometry, hole.hole_number, rotation_deg=0.0)
        assert room == pytest.approx(hole.hole_number * step)


def test_without_rotation_target_hole_is_the_marked_one() -> None:
    geometry = _geometry(target_hole_number=7)
    assert target_hole_for_trial(geometry, rotation_deg=0.0) == 7


def test_rotated_trials_share_target_room_position_with_different_index() -> None:
    # Cenário 1: rotações 0° e 90° -> índices de alvo diferentes, mesma posição na sala.
    geometry = _geometry(hole_count=20, target_hole_number=3)

    target_at_0 = target_hole_for_trial(geometry, rotation_deg=0.0)
    target_at_90 = target_hole_for_trial(geometry, rotation_deg=90.0)

    assert target_at_0 != target_at_90
    assert target_at_90 == (3 - 5) % 20  # 90° = 5 passos de 18°
    room_at_0 = hole_to_room_angle(geometry, target_at_0, rotation_deg=0.0)
    room_at_90 = hole_to_room_angle(geometry, target_at_90, rotation_deg=90.0)
    assert room_at_0 == pytest.approx(room_at_90)
    assert room_at_0 == pytest.approx(target_room_angle(geometry))


def test_displaced_camera_keeps_room_angles() -> None:
    # Câmera girada 30° e transladada entre dias: nova montagem, com o buraco 0
    # arrastado até o mesmo buraco físico de referência -> mesmos ângulos de sala.
    day_1 = _geometry(start_angle_deg=0.0, target_hole_number=5)
    day_2 = _geometry(
        start_angle_deg=30.0, target_hole_number=5, center_x_px=300.0, center_y_px=260.0
    )

    assert day_1.holes[5].angle_deg != pytest.approx(day_2.holes[5].angle_deg)
    assert target_room_angle(day_1) == pytest.approx(target_room_angle(day_2))
    for k in range(day_1.hole_count):
        assert hole_to_room_angle(day_1, k, rotation_deg=0.0) == pytest.approx(
            hole_to_room_angle(day_2, k, rotation_deg=0.0)
        )


def test_room_angle_between_holes_maps_to_nearest() -> None:
    geometry = _geometry(hole_count=8)  # passo de 45°
    assert room_angle_to_hole(geometry, 50.0, rotation_deg=0.0) == 1
    assert room_angle_to_hole(geometry, 340.0, rotation_deg=0.0) == 0  # dá a volta em 360


def test_room_angle_accepts_values_outside_0_360() -> None:
    geometry = _geometry(hole_count=8)
    assert room_angle_to_hole(geometry, -45.0, rotation_deg=0.0) == 7
    assert room_angle_to_hole(geometry, 405.0, rotation_deg=0.0) == 1


@pytest.mark.parametrize("hole_number", [-1, 20])
def test_hole_to_room_angle_rejects_invalid_index(hole_number) -> None:
    with pytest.raises(ValueError, match="Índice de buraco"):
        hole_to_room_angle(_geometry(hole_count=20), hole_number, rotation_deg=0.0)


def test_reference_frame_column_suffix() -> None:
    # RN05: cada coluna de saída identifica seu referencial pelo sufixo.
    assert ReferenceFrame.ROOM.column("target_angle_deg") == "target_angle_deg_room"
    assert ReferenceFrame.PLATFORM.column("target_hole") == "target_hole_platform"
    assert ReferenceFrame.IMAGE.column("angle_deg") == "angle_deg_image"


def test_require_rotations_rejects_and_lists_all_missing_trials() -> None:
    # Cenário 3: trial sem rotação -> análise recusada, identificando o(s) trial(s).
    with pytest.raises(MissingRotationError) as exc_info:
        require_rotations({12: 0.0, 7: None, 3: None})

    assert exc_info.value.trial_ids == [3, 7]
    assert "#3" in str(exc_info.value)
    assert "#7" in str(exc_info.value)
    assert "#12" not in str(exc_info.value)


def test_require_rotations_never_assumes_zero() -> None:
    with pytest.raises(MissingRotationError):
        require_rotations({1: None})


def test_require_rotations_returns_rotations_when_all_present() -> None:
    assert require_rotations({1: 0.0, 2: 90.0}) == {1: 0.0, 2: 90.0}


def test_missing_rotation_error_is_a_value_error() -> None:
    # Compatível com o tratamento genérico de ValueError da CLI.
    assert issubclass(MissingRotationError, ValueError)
