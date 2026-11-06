"""Latência ao alvo com censura (US-16): tempo limite e cálculo puro, sem banco nem vídeo."""

from __future__ import annotations

import math

import numpy as np
import pyarrow as pa
import pytest

from barnes.events.discovery import DiscoveryEvent
from barnes.metrics.latency import (
    CensoredMeasure,
    LatencyConfigError,
    TargetEvent,
    compute_target_latencies,
    load_time_limit,
    target_discovery,
    travelled_distance_cm,
)

LIMIT = 300.0  # tempo limite dos cenários do card; nos testes sempre explícito, nunca do YAML


# --- Tempo limite em configs/ (RN03) -----------------------------------------------------


def _config(tmp_path, body):
    path = tmp_path / "default.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_time_limit_is_read_from_config(tmp_path):
    path = _config(tmp_path, "trial:\n  tempo_limite_s: 300\n")
    assert load_time_limit(path) == 300.0


def test_null_time_limit_is_refused_naming_the_key_and_b5(tmp_path):
    path = _config(tmp_path, "trial:\n  tempo_limite_s: null\n")
    with pytest.raises(LatencyConfigError, match=r"trial\.tempo_limite_s.*B5"):
        load_time_limit(path)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("encontrar: {}\n", "Seção 'trial'"),
        ("trial:\n  tempo_limite_s: trezentos\n", "número"),
        ("trial:\n  tempo_limite_s: true\n", "número"),
        ("trial:\n  tempo_limite_s: .inf\n", "número"),
        ("trial:\n  tempo_limite_s: 0\n", "maior que zero"),
        ("trial:\n  tempo_limite_s: -10\n", "maior que zero"),
    ],
)
def test_invalid_time_limit_is_refused(tmp_path, body, message):
    with pytest.raises(LatencyConfigError, match=message):
        load_time_limit(_config(tmp_path, body))


def test_missing_config_file_is_refused():
    with pytest.raises(LatencyConfigError, match="não encontrado"):
        load_time_limit("nao-existe.yaml")


# --- Eventos do alvo -------------------------------------------------------------------


def test_target_event_states_are_distinct():
    assert TargetEvent.ocorreu(45) == TargetEvent(avaliado=True, t_s=45.0)
    assert TargetEvent.nao_ocorreu() == TargetEvent(avaliado=True, t_s=None)
    assert TargetEvent.nao_avaliado() == TargetEvent(avaliado=False, t_s=None)
    assert TargetEvent.nao_ocorreu() != TargetEvent.nao_avaliado()


def test_event_before_s_is_refused():
    # RN04: tempo zero é S; um t_s negativo indica referência de tempo errada.
    with pytest.raises(ValueError, match="RN04"):
        TargetEvent.ocorreu(-0.5)


def test_unevaluated_event_cannot_have_a_time():
    with pytest.raises(ValueError, match="não avaliado"):
        TargetEvent(avaliado=False, t_s=10.0)


def test_target_discovery_picks_the_target_hole():
    events = [
        DiscoveryEvent(hole_number=3, quadro=100, t_s=4.0, distancia_cm=2.0, angulo_deg=5.0),
        DiscoveryEvent(hole_number=7, quadro=1125, t_s=45.0, distancia_cm=1.0, angulo_deg=3.0),
    ]
    assert target_discovery(events, target_hole_number=7) == TargetEvent.ocorreu(45.0)


def test_target_never_discovered_is_not_occurred_not_unevaluated():
    # O detector D rodou e não achou o alvo: insucesso real, que vira censura.
    events = [DiscoveryEvent(hole_number=3, quadro=1, t_s=4.0, distancia_cm=2.0, angulo_deg=5.0)]
    assert target_discovery(events, target_hole_number=7) == TargetEvent.nao_ocorreu()


# --- Cálculo (RN01, RN02, RN04, RN06; Cenários 1-3) -------------------------------------


def _trajectory(*, end_s=LIMIT, step_s=1.0, speed_cm_s=1.0, valid=None, fps_variavel=False):
    """Linha reta em x a velocidade constante: distância até t = speed * t."""
    t_s = np.arange(0.0, end_s + step_s / 2, step_s)
    n = t_s.size
    x = speed_cm_s * t_s
    valid = np.ones(n, dtype=bool) if valid is None else np.asarray(valid, dtype=bool)
    x = np.where(valid, x, np.nan)
    y = np.where(valid, 0.0, np.nan)
    return pa.table(
        {
            "t_s": t_s,
            "centro_corpo_x_cm_image": x,
            "centro_corpo_y_cm_image": y,
            "centro_corpo_valido": valid,
            "focinho_x_cm_image": x + 2.0,
            "focinho_y_cm_image": y,
            "focinho_valido": valid,
            "base_cauda_x_cm_image": x - 2.0,
            "base_cauda_y_cm_image": y,
            "base_cauda_valido": valid,
            "fps_variavel": np.full(n, fps_variavel),
        }
    )


def test_scenario_1_discovered_and_entered():
    result = compute_target_latencies(
        _trajectory(speed_cm_s=2.0),
        TargetEvent.ocorreu(45.0),
        TargetEvent.ocorreu(58.0),
        tempo_limite_s=LIMIT,
    )
    assert result.as_trials_csv() == {
        "primary_latency": 45.0,
        "primary_distance": 90.0,
        "primary_event": 1,
        "total_latency": 58.0,
        "total_distance": 116.0,
        "total_event": 1,
    }
    assert result.avisos == ()


def test_scenario_2_discovered_but_never_entered():
    result = compute_target_latencies(
        _trajectory(),
        TargetEvent.ocorreu(90.0),
        TargetEvent.nao_ocorreu(),
        tempo_limite_s=LIMIT,
    )
    assert result.primary == CensoredMeasure(latency_s=90.0, distance_cm=90.0, event=1)
    # Censurado: latência = tempo limite, distância percorrida até o tempo limite.
    assert result.total == CensoredMeasure(latency_s=300.0, distance_cm=300.0, event=0)


def test_scenario_3_never_discovered():
    result = compute_target_latencies(
        _trajectory(),
        TargetEvent.nao_ocorreu(),
        TargetEvent.nao_ocorreu(),
        tempo_limite_s=LIMIT,
    )
    row = result.as_trials_csv()
    assert row["primary_latency"] == row["total_latency"] == 300.0
    assert row["primary_event"] == row["total_event"] == 0
    assert row["primary_distance"] == row["total_distance"] == 300.0


def test_no_censored_trial_is_discarded():
    # RN02 / SCRUM-198: todo trial da entrada sai na saída, censurado ou não, com
    # latência numérica e event explícito — nunca omitido, nunca None.
    trials = {
        "encontrou_e_entrou": (TargetEvent.ocorreu(45.0), TargetEvent.ocorreu(58.0)),
        "so_descobriu": (TargetEvent.ocorreu(90.0), TargetEvent.nao_ocorreu()),
        "nunca_encontrou": (TargetEvent.nao_ocorreu(), TargetEvent.nao_ocorreu()),
        "depois_do_limite": (TargetEvent.ocorreu(310.0), TargetEvent.ocorreu(320.0)),
    }
    rows = {
        name: compute_target_latencies(
            _trajectory(end_s=330.0), d, e, tempo_limite_s=LIMIT
        ).as_trials_csv()
        for name, (d, e) in trials.items()
    }
    assert rows.keys() == trials.keys()
    for row in rows.values():
        for column in ("primary_latency", "total_latency", "primary_event", "total_event"):
            assert row[column] is not None
            assert not (isinstance(row[column], float) and math.isnan(row[column]))
    censored = [
        name for name, row in rows.items() if 0 in (row["primary_event"], row["total_event"])
    ]
    assert censored == ["so_descobriu", "nunca_encontrou", "depois_do_limite"]


def test_event_after_time_limit_is_censored_at_the_limit():
    result = compute_target_latencies(
        _trajectory(end_s=330.0),
        TargetEvent.ocorreu(310.0),
        TargetEvent.nao_ocorreu(),
        tempo_limite_s=LIMIT,
    )
    assert result.primary == CensoredMeasure(latency_s=300.0, distance_cm=300.0, event=0)
    assert any("depois do tempo limite" in aviso for aviso in result.avisos)


def test_event_exactly_at_the_limit_is_observed():
    result = compute_target_latencies(
        _trajectory(), TargetEvent.ocorreu(300.0), TargetEvent.nao_ocorreu(), tempo_limite_s=LIMIT
    )
    assert result.primary.event == 1


def test_missing_entry_detector_is_not_censoring():
    # US-13 ainda não existe: total_* fica não calculado, nunca censurado em 300.
    result = compute_target_latencies(
        _trajectory(),
        TargetEvent.ocorreu(45.0),
        TargetEvent.nao_avaliado(),
        tempo_limite_s=LIMIT,
    )
    assert result.primary == CensoredMeasure(latency_s=45.0, distance_cm=45.0, event=1)
    assert result.total == CensoredMeasure(latency_s=None, distance_cm=None, event=None)
    assert not result.total.calculado
    assert any("não é censura" in aviso and "US-13" in aviso for aviso in result.avisos)


def test_time_zero_is_s_samples_before_it_do_not_count():
    # RN04: amostras com t_s < 0 (antes da soltura) não entram na distância.
    table = _trajectory(end_s=60.0)
    t_s = table.column("t_s").to_numpy() - 10.0  # trajetória começando em -10 s
    table = table.set_column(0, "t_s", pa.array(t_s))
    result = compute_target_latencies(
        table, TargetEvent.ocorreu(20.0), TargetEvent.nao_avaliado(), tempo_limite_s=LIMIT
    )
    # x = t_s + 10; de t=0 (x=10) a t=20 (x=30) são 20 cm, não 30.
    assert result.primary.distance_cm == pytest.approx(20.0)


def test_variable_fps_is_flagged():
    result = compute_target_latencies(
        _trajectory(fps_variavel=True),
        TargetEvent.ocorreu(45.0),
        TargetEvent.ocorreu(58.0),
        tempo_limite_s=LIMIT,
    )
    assert result.fps_variavel
    assert any("fps variável" in aviso for aviso in result.avisos)


def test_entry_without_discovery_is_flagged():
    result = compute_target_latencies(
        _trajectory(), TargetEvent.nao_ocorreu(), TargetEvent.ocorreu(58.0), tempo_limite_s=LIMIT
    )
    assert result.total.event == 1
    assert any("sem descoberta" in aviso for aviso in result.avisos)


def test_entry_before_discovery_is_flagged():
    result = compute_target_latencies(
        _trajectory(), TargetEvent.ocorreu(60.0), TargetEvent.ocorreu(58.0), tempo_limite_s=LIMIT
    )
    assert any("antes da descoberta" in aviso for aviso in result.avisos)


def test_trajectory_shorter_than_limit_is_flagged_when_censored():
    result = compute_target_latencies(
        _trajectory(end_s=200.0),
        TargetEvent.ocorreu(90.0),
        TargetEvent.nao_ocorreu(),
        tempo_limite_s=LIMIT,
    )
    assert result.total == CensoredMeasure(latency_s=300.0, distance_cm=200.0, event=0)
    assert any("termina em 200.00 s" in aviso for aviso in result.avisos)


def test_distance_uses_the_chosen_point():
    table = _trajectory()
    # O focinho anda o mesmo que o centro do corpo (deslocado de 2 cm), então dá igual.
    for ponto in ("centro_corpo", "focinho", "base_cauda"):
        result = compute_target_latencies(
            table,
            TargetEvent.ocorreu(45.0),
            TargetEvent.nao_avaliado(),
            tempo_limite_s=LIMIT,
            ponto_distancia=ponto,
        )
        assert result.primary.distance_cm == pytest.approx(45.0)
        assert result.ponto_distancia == ponto


@pytest.mark.parametrize("limit", [0, -1, float("nan"), float("inf"), True])
def test_invalid_explicit_limit_is_refused(limit):
    with pytest.raises(ValueError, match="tempo limite"):
        compute_target_latencies(
            _trajectory(),
            TargetEvent.nao_ocorreu(),
            TargetEvent.nao_ocorreu(),
            tempo_limite_s=limit,
        )


def test_unknown_point_and_missing_columns_are_refused():
    with pytest.raises(ValueError, match="desconhecido"):
        compute_target_latencies(
            _trajectory(),
            TargetEvent.nao_ocorreu(),
            TargetEvent.nao_ocorreu(),
            tempo_limite_s=LIMIT,
            ponto_distancia="orelha",
        )
    with pytest.raises(ValueError, match="fps_variavel"):
        compute_target_latencies(
            _trajectory().drop_columns(["fps_variavel"]),
            TargetEvent.nao_ocorreu(),
            TargetEvent.nao_ocorreu(),
            tempo_limite_s=LIMIT,
        )


# --- Distância percorrida (RN06) --------------------------------------------------------


def test_distance_bridges_pose_gaps_in_a_straight_line():
    t_s = np.array([0.0, 1.0, 2.0, 3.0])
    x = np.array([0.0, np.nan, np.nan, 3.0])
    y = np.array([0.0, np.nan, np.nan, 4.0])
    valid = np.array([True, False, False, True])
    assert travelled_distance_cm(t_s, x, y, valid, until_s=3.0) == pytest.approx(5.0)


def test_distance_without_valid_pose_is_unknown_not_zero():
    t_s = np.array([0.0, 1.0])
    nan = np.array([np.nan, np.nan])
    valid = np.array([False, False])
    assert travelled_distance_cm(t_s, nan, nan, valid, until_s=1.0) is None
