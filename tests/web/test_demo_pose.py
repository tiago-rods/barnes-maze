"""Modo demo do wizard web: a pose sintética precisa disparar o pipeline real.

Não é teste de aceite de nada do laboratório — só garante que a trajetória
de demonstração, passada pelas funções de produção com os limiares de
`configs/default.yaml`, produz D e E no alvo, checagens antes dele e uma
estratégia classificada (senão a apresentação mostraria só "não calculado").
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))  # `web/` fica fora de `src/` (pythonpath do pytest)

from barnes.events.discovery import detect_discoveries, load_discovery_params
from barnes.events.entry import detect_entries, load_entry_params
from barnes.events.sequence import build_sequence, to_visit_sequence
from barnes.geometry.holes import generate_holes
from barnes.geometry.reference_frame import target_room_angle
from barnes.io.trim import interval_from_seconds
from barnes.metrics.errors import compute_errors, load_error_definition
from barnes.pose.annotations import KEYPOINTS
from barnes.pose.series import PoseFrames, build_series
from barnes.pose.training import load_model_manifest
from barnes.strategy.classification import (
    classify_strategy,
    load_strategy_thresholds,
)
from barnes.strategy.signals import (
    compute_angular_adjacency,
    count_center_crossings,
)
from web.backend.app.demo_pose import (
    demo_model_id,
    ensure_demo_model,
    is_demo_model,
    synthetic_backend_factory,
    synthetic_pose,
)

CONFIG = ROOT / "configs" / "default.yaml"
FPS = 24.0
N_FRAMES = 360
CM_PER_PX = 10 / 171.79  # escala da montagem de exemplo (px_per_10cm ≈ 171.8)


@pytest.fixture
def geometry():
    return generate_holes(
        center_x_px=300.0,
        center_y_px=300.0,
        platform_radius_px=230.0,
        hole_count=20,
        start_angle_deg=0.0,
        target_hole_number=7,
        hole_radius_px=15.0,
    )


def _series(geometry):
    points, scores = synthetic_pose(geometry, CM_PER_PX, FPS, N_FRAMES)
    frames = np.arange(N_FRAMES)
    pose = PoseFrames(
        frames=frames,
        x_px={name: points[:, i, 0] for i, name in enumerate(KEYPOINTS)},
        y_px={name: points[:, i, 1] for i, name in enumerate(KEYPOINTS)},
        confidence={name: scores[:, i] for i, name in enumerate(KEYPOINTS)},
    )
    interval = interval_from_seconds(0.0, (N_FRAMES - 1) / FPS, FPS, manually_adjusted=True)
    return build_series(
        pose,
        trial_id=1,
        execucao_id=1,
        expected_frames=(0, N_FRAMES - 1),
        fps=FPS,
        interval=interval,
        fps_variable=False,
        cm_per_px=CM_PER_PX,
        content_hash="demo-test",
        model_id=demo_model_id(1),
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_trajetoria_sintetica_gera_descoberta_e_entrada_no_alvo(geometry) -> None:
    table = _series(geometry)
    target = geometry.target_hole.hole_number
    discoveries = detect_discoveries(table, geometry, CM_PER_PX, load_discovery_params(CONFIG))
    entries = detect_entries(
        table,
        geometry,
        CM_PER_PX,
        load_entry_params(CONFIG),
        discoveries,
        trial_id=1,
        target_hole_number=target,
    )
    assert target in {event.hole_number for event in discoveries}
    entered = [entry.hole_number for entry in sorted(entries, key=lambda e: e.t_s)]
    assert entered[-1] == target
    assert len(entered) == 4  # três checagens antes do alvo + o alvo

    sequence = to_visit_sequence(
        build_sequence(entries, geometry=geometry, rotation_deg=0.0, target_hole_number=target)
    )
    errors = compute_errors(sequence, load_error_definition(CONFIG))
    assert errors.ate_alvo == 3

    thresholds = load_strategy_thresholds(CONFIG)
    until_s = next(item.inicio_s for item in sequence.itens if item.alvo)
    crossings = count_center_crossings(
        table,
        geometry,
        CM_PER_PX,
        zona_raio_frac=thresholds.centro_zona_raio_frac,
        until_s=until_s,
    )
    adjacency = compute_angular_adjacency(
        sequence,
        target_angle_deg_room=target_room_angle(geometry),
        adjacencia_angular_graus=thresholds.adjacencia_angular_graus,
    )
    result = classify_strategy(crossings, adjacency, errors, thresholds=thresholds)
    assert result.categoria is not None
    assert result.categoria.value == "serial"


def test_backend_sintetico_responde_em_lotes_na_ordem(geometry) -> None:
    backend = synthetic_backend_factory(geometry, CM_PER_PX, FPS)(None, device="cpu", batch_size=7)
    images = np.zeros((7, 4, 4, 3), dtype=np.uint8)
    first, _ = backend.predict(images)
    second, scores = backend.predict(images)
    expected, _ = synthetic_pose(geometry, CM_PER_PX, FPS, 1024)
    np.testing.assert_allclose(np.concatenate([first, second]), expected[:14])
    assert scores.shape == (7, 3)


def test_modelo_demo_e_aceito_pela_inferencia_e_identificado(tmp_path) -> None:
    model_dir = ensure_demo_model(5, root=tmp_path)
    manifest = load_model_manifest(model_dir)
    assert manifest["model_id"] == "DEMO-SINTETICO-m5"
    assert is_demo_model(manifest["model_id"])
    assert not is_demo_model("modelo-real-2026")
    assert ensure_demo_model(5, root=tmp_path) == model_dir  # idempotente
