from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import yaml

from barnes.events.discovery import DiscoveryParams, detect_discoveries
from barnes.events.entry import EntryParams, detect_entries
from barnes.events.sequence import build_sequence, to_visit_sequence
from barnes.geometry.holes import generate_holes
from barnes.io.trim import interval_from_seconds
from barnes.io.video import load_trial_video
from barnes.metrics import process_trial
from barnes.metrics.displacement import compute_displacement
from barnes.metrics.errors import ErrorCriterion, ErrorDefinition, compute_errors
from barnes.metrics.latency import TargetEvent, compute_target_latencies, target_discovery
from barnes.pose.series import PoseFrames, build_series

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VIDEO_PATH = FIXTURES_DIR / "trial_referencia.mp4"
EXPECTED_PATH = FIXTURES_DIR / "trial_referencia_esperado.yaml"

SEG_A = 20
DWELL_A = 10
SEG_C = 40
DWELL_C = 15
NOSE_OFFSET_PX = 4.0


class RegressionFailures:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def check(self, nome: str, atual, esperado, tol: float) -> None:
        if atual is None and esperado is None:
            return
        if atual is None or esperado is None or abs(float(atual) - float(esperado)) > tol:
            self.messages.append(f"{nome}: esperado {esperado!r}, obtido {atual!r}")

    def check_eq(self, nome: str, atual, esperado) -> None:
        if atual != esperado:
            self.messages.append(f"{nome}: esperado {esperado!r}, obtido {atual!r}")

    def finish(self) -> None:
        assert not self.messages, "Regressão detectada:\n" + "\n".join(self.messages)


def _load_expected() -> dict:
    return yaml.safe_load(EXPECTED_PATH.read_text(encoding="utf-8"))


def _build_geometry(expected: dict):
    g = expected["geometria"]
    return generate_holes(
        center_x_px=g["center_x_px"],
        center_y_px=g["center_y_px"],
        platform_radius_px=g["platform_radius_px"],
        hole_count=g["hole_count"],
        start_angle_deg=g["start_angle_deg"],
        target_hole_number=g["target_hole_number"],
        hole_radius_px=g["hole_radius_px"],
    )


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _scenario_path(geometry, expected: dict) -> list[tuple[float, float]]:
    release = (expected["geometria"]["center_x_px"], expected["geometria"]["center_y_px"])
    wrong_hole = geometry.holes[2]
    target_hole = geometry.target_hole
    path: list[tuple[float, float]] = [release] * expected["video"]["pre_release_frames"]
    for i in range(SEG_A + 1):
        path.append(_lerp(release, (wrong_hole.x_px, wrong_hole.y_px), i / SEG_A))
    for _ in range(DWELL_A):
        path.append((wrong_hole.x_px, wrong_hole.y_px))
    for i in range(1, SEG_C + 1):
        path.append(
            _lerp((wrong_hole.x_px, wrong_hole.y_px), (target_hole.x_px, target_hole.y_px), i / SEG_C)
        )
    for _ in range(DWELL_C):
        path.append((target_hole.x_px, target_hole.y_px))
    return path


def _headings(path: list[tuple[float, float]]) -> list[float]:
    headings = [0.0]
    last = 0.0
    for i in range(1, len(path)):
        dx = path[i][0] - path[i - 1][0]
        dy = path[i][1] - path[i - 1][1]
        if dx != 0 or dy != 0:
            last = math.degrees(math.atan2(dy, dx)) % 360.0
        headings.append(last)
    headings[0] = headings[1] if len(headings) > 1 else 0.0
    return headings


def _build_trajectory_table(expected: dict, geometry, path: list[tuple[float, float]]):
    pre = expected["video"]["pre_release_frames"]
    interval_path = path[pre:]
    headings = _headings(path)[pre:]

    centro_x = np.array([p[0] for p in interval_path], dtype=np.float64)
    centro_y = np.array([p[1] for p in interval_path], dtype=np.float64)
    theta_rad = np.radians(np.array(headings))
    focinho_x = centro_x + NOSE_OFFSET_PX * np.cos(theta_rad)
    focinho_y = centro_y + NOSE_OFFSET_PX * np.sin(theta_rad)
    cauda_x = centro_x - NOSE_OFFSET_PX * np.cos(theta_rad)
    cauda_y = centro_y - NOSE_OFFSET_PX * np.sin(theta_rad)

    start_frame = expected["intervalo"]["start_frame"]
    end_frame = expected["intervalo"]["end_frame"]
    frames = np.arange(start_frame, end_frame + 1)
    conf = np.ones(len(frames))

    pose = PoseFrames(
        frames=frames,
        x_px={"focinho": focinho_x, "centro_corpo": centro_x, "base_cauda": cauda_x},
        y_px={"focinho": focinho_y, "centro_corpo": centro_y, "base_cauda": cauda_y},
        confidence={"focinho": conf, "centro_corpo": conf, "base_cauda": conf},
    )

    interval = interval_from_seconds(
        expected["intervalo"]["start_s"],
        expected["intervalo"]["end_s"],
        expected["video"]["fps"],
        manually_adjusted=True,
    )

    table = build_series(
        pose,
        trial_id=1,
        execucao_id=1,
        expected_frames=(start_frame, end_frame),
        fps=expected["video"]["fps"],
        interval=interval,
        fps_variable=False,
        cm_per_px=expected["cm_per_px"],
        content_hash="trial-referencia-us28",
        model_id="synthetic-fixture",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    return table, interval


@pytest.fixture(scope="module")
def expected() -> dict:
    return _load_expected()


@pytest.fixture(scope="module")
def pipeline_output(expected: dict) -> dict:
    geometry = _build_geometry(expected)
    path = _scenario_path(geometry, expected)
    table, interval = _build_trajectory_table(expected, geometry, path)
    target_hole_number = geometry.target_hole.hole_number

    discovery_params = DiscoveryParams(
        distance_cm=expected["limiares_teste"]["encontrar"]["distancia_cm"],
        angle_deg=expected["limiares_teste"]["encontrar"]["angulo_graus"],
    )
    entry_params = EntryParams(
        radius_factor=expected["limiares_teste"]["entrar"]["raio_fator"],
        minimum_duration_s=expected["limiares_teste"]["entrar"]["duracao_minima_s"],
    )
    error_def = ErrorDefinition(criterio=ErrorCriterion(expected["limiares_teste"]["erro"]["criterio"]))
    tempo_limite_s = expected["limiares_teste"]["trial"]["tempo_limite_s"]

    discoveries = detect_discoveries(table, geometry, expected["cm_per_px"], discovery_params)
    entries = detect_entries(
        table,
        geometry,
        expected["cm_per_px"],
        entry_params,
        discoveries,
        trial_id=1,
        target_hole_number=target_hole_number,
    )
    sequence = build_sequence(
        entries,
        geometry=geometry,
        rotation_deg=expected["rotation_deg"],
        target_hole_number=target_hole_number,
    )
    visit_sequence = to_visit_sequence(sequence)
    errors = compute_errors(visit_sequence, error_def)

    target_d = target_discovery(discoveries, target_hole_number)
    target_entries = [e for e in entries if e.hole_number == target_hole_number]
    target_e = (
        TargetEvent.ocorreu(target_entries[0].t_s) if target_entries else TargetEvent.nao_ocorreu()
    )
    latencies = compute_target_latencies(table, target_d, target_e, tempo_limite_s=tempo_limite_s)

    all_times = [i / expected["video"]["fps"] for i in range(len(path))]
    ideal_px = math.hypot(
        geometry.target_hole.x_px - expected["geometria"]["center_x_px"],
        geometry.target_hole.y_px - expected["geometria"]["center_y_px"],
    )
    trajeto = process_trial(
        expected["cm_per_px"],
        path,
        all_times,
        frame_size=(expected["video"]["frame_width"], expected["video"]["frame_height"]),
        interval=interval,
        ideal_distance_px=ideal_px,
    )

    coverage = float(table.column("pose_valida").to_numpy().mean())
    deslocamento = compute_displacement(table)

    return {
        "table": table,
        "discoveries": discoveries,
        "entries": entries,
        "sequence": sequence,
        "errors": errors,
        "latencies": latencies,
        "trajeto": trajeto,
        "coverage": coverage,
        "deslocamento": deslocamento,
    }


def test_video_de_referencia_carrega(expected: dict) -> None:
    video = load_trial_video(VIDEO_PATH)
    assert video.width == expected["video"]["frame_width"]
    assert video.height == expected["video"]["frame_height"]
    assert video.frame_count == expected["video"]["frame_count"]
    assert video.fps_real == pytest.approx(expected["video"]["fps"], rel=0.05)


def test_recorte_us03_nada_fora_do_intervalo(expected: dict, pipeline_output: dict) -> None:
    start_frame = expected["intervalo"]["start_frame"]
    end_frame = expected["intervalo"]["end_frame"]
    for discovery in pipeline_output["discoveries"]:
        assert start_frame <= discovery.quadro <= end_frame
    for entry in pipeline_output["entries"]:
        assert start_frame <= entry.quadro <= end_frame
    quadros = pipeline_output["table"].column("quadro").to_numpy()
    assert quadros.min() == start_frame
    assert quadros.max() == end_frame
    assert pipeline_output["trajeto"]["samples_outside_interval"] == expected["video"]["pre_release_frames"]


def test_cobertura_de_pose(expected: dict, pipeline_output: dict) -> None:
    tol = expected["tolerancia_absoluta"]
    failures = RegressionFailures()
    failures.check("pose.cobertura", pipeline_output["coverage"], expected["pose"]["cobertura"], tol)
    failures.finish()


def test_descobertas(expected: dict, pipeline_output: dict) -> None:
    tol = expected["tolerancia_absoluta"]
    failures = RegressionFailures()
    esperado = expected["descobertas"]
    obtido = pipeline_output["discoveries"]
    failures.check_eq("descobertas.quantidade", len(obtido), len(esperado))
    for i, (e, o) in enumerate(zip(esperado, obtido, strict=False)):
        failures.check_eq(f"descobertas[{i}].buraco", o.hole_number, e["buraco"])
        failures.check_eq(f"descobertas[{i}].quadro", o.quadro, e["quadro"])
        failures.check(f"descobertas[{i}].t_s", o.t_s, e["t_s"], tol)
        failures.check(f"descobertas[{i}].distancia_cm", o.distancia_cm, e["distancia_cm"], tol)
        failures.check(f"descobertas[{i}].angulo_deg", o.angulo_deg, e["angulo_deg"], tol)
    failures.finish()


def test_entradas(expected: dict, pipeline_output: dict) -> None:
    tol = expected["tolerancia_absoluta"]
    failures = RegressionFailures()
    esperado = expected["entradas"]
    obtido = pipeline_output["entries"]
    failures.check_eq("entradas.quantidade", len(obtido), len(esperado))
    for i, (e, o) in enumerate(zip(esperado, obtido, strict=False)):
        failures.check_eq(f"entradas[{i}].buraco", o.hole_number, e["buraco"])
        failures.check_eq(f"entradas[{i}].quadro", o.quadro, e["quadro"])
        failures.check(f"entradas[{i}].t_s", o.t_s, e["t_s"], tol)
        failures.check(f"entradas[{i}].confirmado_em_s", o.confirmed_at_s, e["confirmado_em_s"], tol)
        failures.check(f"entradas[{i}].dwell_s", o.dwell_s, e["dwell_s"], tol)
        failures.check(f"entradas[{i}].total_latency", o.total_latency, e["total_latency"], tol)
        failures.check(
            f"entradas[{i}].total_distance_cm", o.total_distance_cm, e["total_distance_cm"], tol
        )
    failures.finish()


def test_sequencia(expected: dict, pipeline_output: dict) -> None:
    tol = expected["tolerancia_absoluta"]
    failures = RegressionFailures()
    esperado = expected["sequencia"]
    obtido = pipeline_output["sequence"]
    failures.check_eq("sequencia.quantidade", len(obtido), len(esperado))
    for i, (e, o) in enumerate(zip(esperado, obtido, strict=False)):
        failures.check_eq(f"sequencia[{i}].ordem", o.ordem, e["ordem"])
        failures.check_eq(f"sequencia[{i}].buraco_platform", o.buraco_platform, e["buraco_platform"])
        failures.check(f"sequencia[{i}].angulo_deg_room", o.angulo_deg_room, e["angulo_deg_room"], tol)
        failures.check(f"sequencia[{i}].inicio_s", o.inicio_s, e["inicio_s"], tol)
        failures.check_eq(f"sequencia[{i}].alvo", o.alvo, e["alvo"])
    failures.finish()


def test_erros(expected: dict, pipeline_output: dict) -> None:
    failures = RegressionFailures()
    esperado = expected["erros"]
    obtido = pipeline_output["errors"]
    failures.check_eq("erros.total_errors", obtido.total, esperado["total_errors"])
    failures.check_eq("erros.primary_errors", obtido.ate_alvo, esperado["primary_errors"])
    failures.check_eq("erros.primary_censurado", obtido.primary_censurado, esperado["primary_censurado"])
    failures.finish()


def test_latencias(expected: dict, pipeline_output: dict) -> None:
    tol = expected["tolerancia_absoluta"]
    failures = RegressionFailures()
    esperado = expected["latencias"]
    obtido = pipeline_output["latencies"].as_trials_csv()
    for chave in esperado:
        failures.check(f"latencias.{chave}", obtido[chave], esperado[chave], tol)
    failures.finish()


def test_trajeto(expected: dict, pipeline_output: dict) -> None:
    tol = expected["tolerancia_absoluta"]
    failures = RegressionFailures()
    esperado = expected["trajeto"]
    obtido = pipeline_output["trajeto"]
    for chave in esperado:
        failures.check(f"trajeto.{chave}", obtido[chave], esperado[chave], tol)
    failures.finish()


def test_deslocamento_us18(expected: dict, pipeline_output: dict) -> None:
    """US-18 lê a série do contrato (US-09), não o CSV em pixels da US-02."""
    tol = expected["tolerancia_absoluta"]
    failures = RegressionFailures()
    esperado = expected["deslocamento"]
    obtido = pipeline_output["deslocamento"]
    for chave in ("distance_cm", "mean_speed_cm_s", "duration_s", "interpolated_fraction"):
        failures.check(f"deslocamento.{chave}", getattr(obtido, chave), esperado[chave], tol)
    failures.check_eq("deslocamento.frames_used", obtido.frames_used, esperado["frames_used"])
    failures.check_eq("deslocamento.ponto", obtido.ponto, esperado["ponto"])
    failures.check_eq(
        "deslocamento.speed_time_base_approx",
        obtido.as_export_columns()["speed_time_base_approx"],
        esperado["speed_time_base_approx"],
    )
    # As duas rotas (US-02 em px, US-18 pela série em cm) devem concordar sem lacunas.
    trajeto = pipeline_output["trajeto"]
    failures.check(
        "deslocamento.distance_cm vs trajeto", obtido.distance_cm, trajeto["distance_cm"], tol
    )
    failures.check(
        "deslocamento.mean_speed_cm_s vs trajeto",
        obtido.mean_speed_cm_s,
        trajeto["mean_speed_cm_s"],
        tol,
    )
    failures.finish()
