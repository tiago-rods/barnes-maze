"""Fixtures do US-06: geometria, protocolo e um trial sintético com um "animal" andando."""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
import pytest

from barnes.geometry.holes import MazeGeometry, generate_holes
from barnes.pose.protocol import AnnotationProtocol, SplitProportions
from barnes.pose.regions import Region, RegionParams

FRAME_SIZE = (320, 240)
CENTER = (160.0, 120.0)
RING_RADIUS = 90.0
HOLE_RADIUS = 8.0
HOLE_COUNT = 12
ANIMAL_RADIUS = 10
SEGMENT_FRAMES = 40


@pytest.fixture
def geometry() -> MazeGeometry:
    return generate_holes(
        center_x_px=CENTER[0],
        center_y_px=CENTER[1],
        platform_radius_px=RING_RADIUS,
        hole_count=HOLE_COUNT,
        start_angle_deg=0.0,
        target_hole_number=0,
        hole_radius_px=HOLE_RADIUS,
    )


@pytest.fixture
def region_params() -> RegionParams:
    return RegionParams(center_radius_frac=0.5, hole_margin_radii=1.0)


@pytest.fixture
def protocol(region_params: RegionParams) -> AnnotationProtocol:
    return AnnotationProtocol(
        regions=region_params,
        frames_per_region={Region.CENTRO: 3, Region.BORDA: 3, Region.BURACO: 3},
        min_gap_frames=5,
        split=SplitProportions(treino=0.7, validacao=0.15, teste=0.15),
        seed=0,
    )


def _polar(radius: float, angle_deg: float) -> tuple[float, float]:
    angle = math.radians(angle_deg)
    return CENTER[0] + radius * math.cos(angle), CENTER[1] + radius * math.sin(angle)


def animal_path() -> list[tuple[float, float]]:
    """Posição do animal em cada quadro: centro, depois borda entre buracos, depois um buraco.

    Em cada trecho o animal se move um pouco, para não sobrar na mediana do fundo.
    """
    path = []
    for i in range(SEGMENT_FRAMES):  # centro: pequeno círculo em torno do centro
        path.append(_polar(12.0, i * 9.0))
    for i in range(SEGMENT_FRAMES):  # borda: entre os buracos de 0° e 30°, oscilando
        path.append(_polar(RING_RADIUS + 3.0 * math.sin(i), 15.0 + 2.0 * math.sin(i / 3)))
    for i in range(SEGMENT_FRAMES):  # buraco: junto ao buraco de 90°
        path.append(_polar(RING_RADIUS - 6.0 + 2.0 * math.sin(i), 90.0 + 2.0 * math.cos(i / 3)))
    return path


@pytest.fixture
def trial_video(tmp_path: Path, geometry: MazeGeometry) -> Path:
    """Trial sintético: plataforma clara, buracos escuros e um animal escuro em movimento."""
    path = tmp_path / "trial.mp4"
    width, height = FRAME_SIZE
    base = np.full((height, width, 3), 30, dtype=np.uint8)
    cv2.circle(base, (int(CENTER[0]), int(CENTER[1])), int(RING_RADIUS + 20), (200, 200, 200), -1)
    for hole in geometry.holes:
        cv2.circle(base, (round(hole.x_px), round(hole.y_px)), int(HOLE_RADIUS), (30, 30, 30), -1)

    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 25.0, FRAME_SIZE)
    assert writer.isOpened()
    try:
        for x, y in animal_path():
            frame = base.copy()
            cv2.circle(frame, (round(x), round(y)), ANIMAL_RADIUS, (60, 60, 60), -1)
            writer.write(frame)
    finally:
        writer.release()
    return path


@pytest.fixture
def animal_positions() -> list[tuple[float, float]]:
    """Posição desenhada do animal em cada quadro de `trial_video`."""
    return animal_path()


@pytest.fixture
def segment_frames() -> int:
    """Quadros de cada trecho (centro, borda, buraco) de `trial_video`."""
    return SEGMENT_FRAMES


@pytest.fixture
def dataset_inputs(tmp_path):
    """Três trials pequenos, distintos e rotulados para os contratos US-07."""
    from barnes.pose.annotations import AnnotatedFrame, write_annotations_csv
    from barnes.pose.split import ManifestRow, write_manifest

    frames, rows = [], []
    source = tmp_path / "annotations"
    for index, subset in enumerate(("treino", "validacao", "teste")):
        trial = f"{index + 1:012x}"
        image_dir = source / trial / "quadros"
        image_dir.mkdir(parents=True)
        image = np.full((32, 40, 3), index * 40, dtype=np.uint8)
        cv2.imwrite(str(image_dir / "quadro_000005.png"), image)
        (image_dir.parent / "amostragem.csv").write_text(
            f"trial,maze_config_id,quadro\n{trial},7,5\n", encoding="utf-8"
        )
        frames.append(AnnotatedFrame(trial, 5, ((10.0, 10.0), (15.0, 15.0), (20.0, 20.0))))
        rows.append(ManifestRow(trial, 5, subset))
    return {
        "annotations_path": write_annotations_csv(frames, source / "anotacoes.csv"),
        "split_path": write_manifest(rows, source / "divisao.csv"),
        "frames_dir": source,
        "output_root": tmp_path / "datasets",
        "maze_config_id": 7,
    }


@pytest.fixture
def fake_exporter():
    """SLP falso somente para testar falhas/integridade, sem depender do backend."""
    import json

    def export(frames, root, output):
        assert all((root / frame["image_path"]).is_file() for frame in frames)
        output.write_text(json.dumps(frames), encoding="utf-8")

    return export
