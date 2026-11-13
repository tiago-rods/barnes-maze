"""Correlação distância automática × manual (US-18 RN06, SCRUM-225): puro, dados sintéticos.

Estes testes verificam a ferramenta, não o aceite: o aceite real depende da medida
manual que ainda não existe (pendências em docs/definicoes-metricas.md).
"""

from __future__ import annotations

import pytest

from barnes.metrics.validation import (
    MANUAL_COLUMNS,
    R_THRESHOLD,
    DistancePair,
    ManualDistanceError,
    blocked_record,
    correlate_distances,
    load_manual_distances,
    render_markdown,
)


def _pairs(manual, auto):
    return [DistancePair(i + 1, m, a) for i, (m, a) in enumerate(zip(manual, auto, strict=True))]


def test_perfect_agreement_passes():
    result = correlate_distances(_pairs([100, 250, 400, 800], [101, 249, 402, 799]))
    assert result.n == 4
    assert result.r == pytest.approx(1.0, abs=1e-4)
    assert result.aprovado
    assert result.limiar == R_THRESHOLD == 0.95


def test_known_r_below_threshold_fails():
    manual = [1.0, 2.0, 3.0, 4.0, 5.0]
    auto = [2.0, 1.0, 4.0, 3.0, 5.0]  # r = 0,8 exato
    result = correlate_distances(_pairs(manual, auto))
    assert result.r == pytest.approx(0.8)
    assert not result.aprovado
    assert result.as_record()["status"] == "reprovado"


def test_scale_bias_is_reported_even_when_r_is_perfect():
    # r não vê escala: automático 20% maior ainda dá r = 1; o viés e o erro relativo sim.
    result = correlate_distances(_pairs([100, 200, 300], [120, 240, 360]))
    assert result.r == pytest.approx(1.0)
    assert result.vies_medio_cm == pytest.approx(40.0)
    assert result.erro_relativo_medio == pytest.approx(0.2)


def test_fewer_than_three_pairs_is_refused():
    with pytest.raises(ValueError, match="ao menos 3"):
        correlate_distances(_pairs([100, 200], [100, 200]))


def test_constant_series_has_undefined_r():
    with pytest.raises(ValueError, match="indefinida"):
        correlate_distances(_pairs([100, 100, 100], [90, 110, 100]))


def test_excluded_trials_are_kept_in_the_record():
    result = correlate_distances(
        _pairs([100, 200, 300], [100, 200, 300]), excluded=[(9, "sem resultado")]
    )
    assert result.as_record()["excluidos"] == [{"trial_id": 9, "motivo": "sem resultado"}]
    assert "9: sem resultado" in render_markdown(result.as_record())


# --- CSV da referência manual -----------------------------------------------------------


def _csv(tmp_path, body):
    path = tmp_path / "manual.csv"
    path.write_text(body, encoding="utf-8")
    return path


def test_manual_csv_round_trip(tmp_path):
    path = _csv(
        tmp_path,
        ",".join(MANUAL_COLUMNS) + "\n3,412.5,Ana,cliques a cada 5 quadros,2026-11-12\n",
    )
    (row,) = load_manual_distances(path)
    assert (row.trial_id, row.distance_cm, row.observador) == (3, 412.5, "Ana")


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("trial_id,distance_cm_manual\n1,2\n", "faltam as colunas"),
        (",".join(MANUAL_COLUMNS) + "\nx,2,a,b,c\n", "não numérico"),
        (",".join(MANUAL_COLUMNS) + "\n1,-2,a,b,c\n", "não negativa"),
        (",".join(MANUAL_COLUMNS) + "\n1,nan,a,b,c\n", "finita"),
        (",".join(MANUAL_COLUMNS) + "\n1,2,a,b,c\n1,3,a,b,c\n", "repetido"),
        (",".join(MANUAL_COLUMNS) + "\n", "nenhuma"),
    ],
)
def test_invalid_manual_csv_is_refused(tmp_path, body, message):
    with pytest.raises(ManualDistanceError, match=message):
        load_manual_distances(_csv(tmp_path, body))


def test_missing_manual_file_is_refused(tmp_path):
    with pytest.raises(ManualDistanceError, match="não encontrada"):
        load_manual_distances(tmp_path / "nao-existe.csv")


def test_blocked_round_renders_without_numbers():
    text = render_markdown(blocked_record("referência manual não entregue"))
    assert "bloqueado" in text and "SCRUM-225" in text and "r =" not in text
