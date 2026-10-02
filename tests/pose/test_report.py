import pytest

from barnes.pose.annotations import AnnotatedFrame
from barnes.pose.regions import Region
from barnes.pose.report import count_by_region, empty_regions


def _frame(index: int, body: tuple[float, float]) -> AnnotatedFrame:
    # Focinho e cauda deslocados de propósito para outras regiões: só o
    # centro do corpo deve definir a região do quadro.
    return AnnotatedFrame("t", index, ((160.0, 120.0), body, (250.0, 120.0)))


def test_counts_by_annotated_body_center(geometry, region_params) -> None:
    hole = geometry.holes[3]
    frames = [
        _frame(0, (160.0, 120.0)),  # centro
        _frame(1, (165.0, 125.0)),  # centro
        _frame(2, (hole.x_px, hole.y_px)),  # buraco
        _frame(3, (160.0 + 105.0, 120.0 + 40.0)),  # borda
    ]
    counts = {c.region: c for c in count_by_region(frames, geometry, region_params)}

    assert counts[Region.CENTRO].frames == 2
    assert counts[Region.BURACO].frames == 1
    assert counts[Region.BORDA].frames == 1
    assert counts[Region.CENTRO].proportion == pytest.approx(0.5)
    assert sum(c.proportion for c in counts.values()) == pytest.approx(1.0)
    assert empty_regions(list(counts.values())) == []


def test_empty_region_is_flagged(geometry, region_params) -> None:
    counts = count_by_region([_frame(0, (160.0, 120.0))], geometry, region_params)
    assert empty_regions(counts) == [Region.BORDA, Region.BURACO]
