import pytest

from barnes.geometry.holes import generate_holes
from barnes.pose.annotations import AnnotatedFrame
from barnes.pose.regions import Region
from barnes.pose.report import (
    MazeConfigResolutionError,
    count_by_region,
    empty_regions,
    resolve_maze_configs,
)


def _frame(index: int, body: tuple[float, float], trial: str = "t") -> AnnotatedFrame:
    # Focinho e cauda deslocados de propósito para outras regiões: só o
    # centro do corpo deve definir a região do quadro.
    return AnnotatedFrame(trial, index, ((160.0, 120.0), body, (250.0, 120.0)))


def test_counts_by_annotated_body_center(geometry, region_params) -> None:
    hole = geometry.holes[3]
    frames = [
        _frame(0, (160.0, 120.0)),  # centro
        _frame(1, (165.0, 125.0)),  # centro
        _frame(2, (hole.x_px, hole.y_px)),  # buraco
        _frame(3, (160.0 + 105.0, 120.0 + 40.0)),  # borda
    ]
    counts = {c.region: c for c in count_by_region(frames, {"t": geometry}, region_params)}

    assert counts[Region.CENTRO].frames == 2
    assert counts[Region.BURACO].frames == 1
    assert counts[Region.BORDA].frames == 1
    assert counts[Region.CENTRO].proportion == pytest.approx(0.5)
    assert sum(c.proportion for c in counts.values()) == pytest.approx(1.0)
    assert empty_regions(list(counts.values())) == []


def test_empty_region_is_flagged(geometry, region_params) -> None:
    counts = count_by_region([_frame(0, (160.0, 120.0))], {"t": geometry}, region_params)
    assert empty_regions(counts) == [Region.BORDA, Region.BURACO]


def test_each_trial_uses_its_own_montagem(geometry, region_params) -> None:
    # Câmera deslocada 60 px num outro dia: o mesmo pixel muda de região.
    shifted = generate_holes(
        center_x_px=geometry.center_x_px + 60.0,
        center_y_px=geometry.center_y_px,
        platform_radius_px=geometry.platform_radius_px,
        hole_count=len(geometry.holes),
        start_angle_deg=0.0,
        target_hole_number=0,
        hole_radius_px=geometry.holes[0].radius_px,
    )
    pixel = (geometry.center_x_px + 60.0, geometry.center_y_px)
    frames = [_frame(0, pixel, trial="dia1"), _frame(0, pixel, trial="dia2")]
    counts = {
        c.region: c.frames
        for c in count_by_region(frames, {"dia1": geometry, "dia2": shifted}, region_params)
    }
    assert counts == {Region.CENTRO: 1, Region.BORDA: 1, Region.BURACO: 0}


def test_resolve_uses_recorded_and_fills_gaps_with_override() -> None:
    assert resolve_maze_configs(["a", "b"], {"a": 3, "b": 4}, override=None) == {"a": 3, "b": 4}
    assert resolve_maze_configs(["a", "b"], {"a": 3, "b": None}, override=3) == {"a": 3, "b": 3}
    assert resolve_maze_configs(["b"], {}, override=5) == {"b": 5}


def test_resolve_refuses_override_that_contradicts_record() -> None:
    with pytest.raises(MazeConfigResolutionError, match="a \\(amostrado com a montagem 3\\)"):
        resolve_maze_configs(["a"], {"a": 3}, override=5)


def test_resolve_refuses_trial_without_montagem() -> None:
    with pytest.raises(MazeConfigResolutionError, match="trial\\(s\\) b"):
        resolve_maze_configs(["a", "b"], {"a": 3}, override=None)
