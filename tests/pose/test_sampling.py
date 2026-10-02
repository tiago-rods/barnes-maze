import csv
import math
from dataclasses import replace
from itertools import pairwise

import cv2
import pytest

from barnes.io.video import load_trial_video, read_frame
from barnes.pose.annotations import trial_key
from barnes.pose.regions import Region
from barnes.pose.sampling import (
    build_background,
    estimate_animal_position,
    export_frames,
    sample_frames,
)


def _sample(trial_video, geometry, protocol, **kwargs):
    metadata = load_trial_video(trial_video)
    return sample_frames(
        trial_video, geometry, protocol, frame_count=metadata.frame_count, scan_step=1, **kwargs
    )


def test_estimated_position_matches_drawn_animal(
    trial_video, geometry, animal_positions, segment_frames
) -> None:
    background = build_background(trial_video, 0, 3 * segment_frames - 1)
    expected = animal_positions
    # Junto ao buraco (quadro 100) a parte do animal sobre o buraco escuro quase
    # não contrasta e o centróide desvia alguns pixels — tolerado: a estimativa
    # só escolhe quadros, e a região continua correta (ver testes de amostragem).
    for index, tolerance_px in ((5, 3.0), (50, 3.0), (100, 5.0)):
        position = estimate_animal_position(read_frame(trial_video, index), background, geometry)
        assert position is not None
        assert math.dist(position, expected[index]) < tolerance_px


def test_no_animal_returns_none(trial_video, geometry, segment_frames) -> None:
    background = build_background(trial_video, 0, 3 * segment_frames - 1)
    assert estimate_animal_position(background, background, geometry) is None


def test_sampling_covers_three_regions(trial_video, geometry, protocol) -> None:
    result = _sample(trial_video, geometry, protocol)
    regions = [frame.region for frame in result.frames]
    for region in Region:
        assert regions.count(region) == 3
    assert result.shortfall == dict.fromkeys(Region, 0)
    assert result.detected == result.scanned


def test_sampled_frames_respect_minimum_gap(trial_video, geometry, protocol) -> None:
    result = _sample(trial_video, geometry, protocol)
    indices = [frame.frame_index for frame in result.frames]
    assert all(b - a >= protocol.min_gap_frames for a, b in pairwise(indices))


def test_same_seed_same_sample(trial_video, geometry, protocol) -> None:
    first = _sample(trial_video, geometry, protocol)
    second = _sample(trial_video, geometry, protocol)
    assert first.frames == second.frames


def test_shortfall_reported_when_region_absent(
    trial_video, geometry, protocol, segment_frames
) -> None:
    # Só o trecho do centro: borda e buraco ficam sem candidatos.
    result = _sample(trial_video, geometry, protocol, end_frame=segment_frames - 1)
    assert result.shortfall[Region.CENTRO] == 0
    assert result.shortfall[Region.BORDA] == 3
    assert result.shortfall[Region.BURACO] == 3


def test_sampling_stays_inside_interval(trial_video, geometry, protocol, segment_frames) -> None:
    result = _sample(trial_video, geometry, protocol, start_frame=segment_frames)
    assert all(frame.frame_index >= segment_frames for frame in result.frames)


def test_invalid_interval_rejected(trial_video, geometry, protocol) -> None:
    with pytest.raises(ValueError, match="Intervalo"):
        _sample(trial_video, geometry, protocol, start_frame=50, end_frame=10)


def test_export_writes_pngs_and_sampling_csv(trial_video, geometry, protocol, tmp_path) -> None:
    metadata = load_trial_video(trial_video)
    result = _sample(trial_video, geometry, replace(protocol, seed=1))
    trial_dir = export_frames(
        trial_video, metadata.content_hash, result.frames, tmp_path / "annotations"
    )

    assert trial_dir.name == trial_key(metadata.content_hash)
    pngs = sorted((trial_dir / "quadros").glob("quadro_*.png"))
    assert len(pngs) == len(result.frames)
    assert cv2.imread(str(pngs[0])).shape[:2] == (240, 320)

    with (trial_dir / "amostragem.csv").open(encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    assert [int(row["quadro"]) for row in rows] == [f.frame_index for f in result.frames]
    assert {row["regiao_estimada"] for row in rows} == {r.value for r in Region}
    assert rows[0]["hash_video"] == metadata.content_hash
