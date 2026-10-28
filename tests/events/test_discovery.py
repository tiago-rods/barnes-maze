"""Detecção do evento de descoberta (US-11): limiares e cálculo puro, sem banco nem vídeo."""

from __future__ import annotations

import pyarrow as pa
import pytest

from barnes.events.discovery import (
    DiscoveryConfigError,
    DiscoveryEvent,
    DiscoveryParams,
    detect_discoveries,
    load_discovery_params,
)
from barnes.geometry.holes import generate_holes

# --- Limiares (RN02) ---------------------------------------------------------------


def _config(tmp_path, body):
    path = tmp_path / "default.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def _encontrar_section(*, distance="10", angle="30"):
    return "\n".join(
        [
            "encontrar:",
            f"  distancia_cm: {distance}",
            f"  angulo_graus: {angle}",
            "",
        ]
    )


def test_valid_config_returns_params(tmp_path):
    path = _config(tmp_path, _encontrar_section(distance="8", angle="25"))
    assert load_discovery_params(path) == DiscoveryParams(distance_cm=8.0, angle_deg=25.0)


def test_missing_file_is_refused():
    with pytest.raises(DiscoveryConfigError, match="não encontrado"):
        load_discovery_params("nao-existe.yaml")


def test_null_distance_is_refused_naming_the_key(tmp_path):
    path = _config(tmp_path, _encontrar_section(distance="null"))
    with pytest.raises(DiscoveryConfigError, match="encontrar.distancia_cm"):
        load_discovery_params(path)


def test_null_angle_is_refused_naming_the_key(tmp_path):
    path = _config(tmp_path, _encontrar_section(angle="null"))
    with pytest.raises(DiscoveryConfigError, match="encontrar.angulo_graus"):
        load_discovery_params(path)


@pytest.mark.parametrize(
    ("body", "key"),
    [
        ("anotacao: {}", "Seção 'encontrar'"),
        (_encontrar_section(distance="dez"), "distancia_cm"),
        (_encontrar_section(distance="0"), "distancia_cm"),
        (_encontrar_section(distance="-5"), "distancia_cm"),
        (_encontrar_section(angle="0"), "angulo_graus"),
        (_encontrar_section(angle="181"), "angulo_graus"),
    ],
)
def test_invalid_config_is_refused(tmp_path, body, key):
    with pytest.raises(DiscoveryConfigError, match=key):
        load_discovery_params(_config(tmp_path, body))


# --- Cálculo (RN01/RN03, Cenários 1/2) ----------------------------------------------

PARAMS = DiscoveryParams(distance_cm=10.0, angle_deg=15.0)


def _geometry():
    # Buraco 0 a (100, 0) px, buraco 1 a (0, 100) px (centro na origem, cm_per_px=1).
    return generate_holes(
        center_x_px=0.0,
        center_y_px=0.0,
        platform_radius_px=100.0,
        hole_count=4,
        start_angle_deg=0.0,
        target_hole_number=0,
        hole_radius_px=5.0,
    )


def _table(*, quadro, t_s, focinho_x, focinho_y, theta, pose_valida=None):
    n = len(quadro)
    return pa.table(
        {
            "quadro": quadro,
            "t_s": t_s,
            "focinho_x_cm_image": focinho_x,
            "focinho_y_cm_image": focinho_y,
            "theta_deg_image": theta,
            "pose_valida": pose_valida if pose_valida is not None else [True] * n,
        }
    )


def test_discovery_detected_on_first_frame_meeting_both_thresholds():
    # Cenário 1: o rato se aproxima do buraco 0 (100, 0) de frente (theta=0).
    table = _table(
        quadro=[10, 11, 12],
        t_s=[0.4, 0.44, 0.48],
        focinho_x=[0.0, 50.0, 95.0],
        focinho_y=[0.0, 0.0, 0.0],
        theta=[0.0, 0.0, 0.0],
    )
    events = detect_discoveries(table, _geometry(), cm_per_px=1.0, params=PARAMS)
    assert events == [
        DiscoveryEvent(hole_number=0, quadro=12, t_s=0.48, distancia_cm=5.0, angulo_deg=0.0)
    ]


def test_passing_close_without_orientation_generates_no_event():
    # Cenário 2: o rato passa a 5 cm do buraco 0, mas de lado (theta=90, nunca aponta pra ele).
    table = _table(
        quadro=[0, 1, 2],
        t_s=[0.0, 0.04, 0.08],
        focinho_x=[95.0, 95.0, 95.0],
        focinho_y=[-20.0, 0.0, 20.0],
        theta=[90.0, 90.0, 90.0],
    )
    events = detect_discoveries(table, _geometry(), cm_per_px=1.0, params=PARAMS)
    assert events == []


def test_only_the_first_qualifying_frame_is_recorded():
    # RN03: duas aproximações qualificadas ao mesmo buraco; só a primeira conta.
    table = _table(
        quadro=[0, 1, 2, 3, 4],
        t_s=[0.0, 0.04, 0.08, 0.12, 0.16],
        focinho_x=[95.0, 200.0, 300.0, 400.0, 92.0],
        focinho_y=[0.0, 0.0, 0.0, 0.0, 0.0],
        theta=[0.0, 0.0, 0.0, 0.0, 0.0],
    )
    events = detect_discoveries(table, _geometry(), cm_per_px=1.0, params=PARAMS)
    assert len(events) == 1
    assert events[0].quadro == 0


def test_invalid_pose_inside_thresholds_does_not_count():
    table = _table(
        quadro=[0, 1],
        t_s=[0.0, 0.04],
        focinho_x=[95.0, 95.0],
        focinho_y=[0.0, 0.0],
        theta=[0.0, 0.0],
        pose_valida=[False, False],
    )
    events = detect_discoveries(table, _geometry(), cm_per_px=1.0, params=PARAMS)
    assert events == []


def test_cm_per_px_scales_hole_positions():
    # Buraco 0 a 100 px; com cm_per_px=0.5, está a 50 cm — focinho a 45 cm fica dentro do limiar.
    table = _table(
        quadro=[0],
        t_s=[0.0],
        focinho_x=[45.0],
        focinho_y=[0.0],
        theta=[0.0],
    )
    events = detect_discoveries(table, _geometry(), cm_per_px=0.5, params=PARAMS)
    assert len(events) == 1
    assert events[0].distancia_cm == pytest.approx(5.0)
