"""Distribuição de estratégias entre sessões ou grupos (US-23): cálculo puro, dados sintéticos.

A US-20 (classificação) ainda não existe: as observações aqui são fabricadas pelo
teste, nunca por um classificador.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

from barnes.stats.contingency import (
    DEFAULT_STRATEGIES,
    MONTE_CARLO_REAMOSTRAGENS,
    MONTE_CARLO_SEMENTE,
    AppliedTest,
    StatsConfigError,
    StrategyObservation,
    build_contingency_table,
    load_min_expected_frequency,
    render_markdown,
    run_independence_test,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
LIMIAR = 5.0  # valor de teste; o de produção fica null em configs/default.yaml


def _obs(linha, **counts) -> list[StrategyObservation]:
    return [
        StrategyObservation(linha, estrategia) for estrategia, n in counts.items() for _ in range(n)
    ]


def _large_sample():
    """4 sessões × 3 estratégias, todas as esperadas >= 5 (Cenário 1)."""
    return (
        _obs(1, spatial=2, serial=8, random=20)
        + _obs(2, spatial=6, serial=10, random=14)
        + _obs(3, spatial=12, serial=10, random=8)
        + _obs(4, spatial=20, serial=6, random=4)
    )


# --- Tabela de contingência (SCRUM-266, SCRUM-270) ----------------------------------------


def test_table_counts_sessions_by_strategy_in_given_order():
    tabela = build_contingency_table(_large_sample())
    assert tabela.dimensao == "sessao"
    assert tabela.linhas == (1, 2, 3, 4)
    assert tabela.categorias == DEFAULT_STRATEGIES == ("spatial", "serial", "random")
    assert tabela.contagens == ((2, 8, 20), (6, 10, 14), (12, 10, 8), (20, 6, 4))
    assert tabela.total == 120
    assert tabela.categorias_ausentes == ()
    assert tabela.avisos == ()


def test_scenario_3_missing_category_appears_with_zeros_and_is_flagged():
    observations = _obs(1, serial=3, random=6) + _obs(2, serial=5, random=4)
    tabela = build_contingency_table(observations)
    assert tabela.categorias == ("spatial", "serial", "random")
    assert tabela.contagens == ((0, 3, 6), (0, 5, 4))
    assert tabela.categorias_ausentes == ("spatial",)
    assert any("'spatial' ausente" in aviso for aviso in tabela.avisos)
    assert "spatial" in render_markdown(
        run_independence_test(tabela, frequencia_esperada_minima=LIMIAR)
    )


def test_missing_category_stays_in_report_but_out_of_the_test():
    observations = (
        _obs(1, serial=8, random=20)
        + _obs(2, serial=10, random=14)
        + _obs(3, serial=10, random=8)
        + _obs(4, serial=12, random=10)
    )
    tabela = build_contingency_table(observations)
    result = run_independence_test(tabela, frequencia_esperada_minima=LIMIAR)
    assert result.categorias_testadas == ("serial", "random")
    reduced = np.array([[8, 20], [10, 14], [10, 8], [12, 10]])
    expected = stats.chi2_contingency(reduced)
    assert result.teste is AppliedTest.QUI_QUADRADO
    assert result.estatistica == pytest.approx(expected.statistic)
    assert result.as_record()["tabela"]["contagens"][0] == [0, 8, 20]


def test_expected_session_without_trials_is_a_zero_row():
    tabela = build_contingency_table(_obs(1, serial=2) + _obs(3, random=2), linhas=[1, 2, 3, 4])
    assert tabela.linhas == (1, 2, 3, 4)
    assert tabela.contagens[1] == (0, 0, 0)
    assert tabela.linhas_vazias == (2, 4)
    assert any("Sessão 2" in aviso for aviso in tabela.avisos)


def test_unclassified_trials_are_counted_and_left_out():
    observations = _obs(1, serial=2, random=1) + [StrategyObservation(1, None)] * 2
    tabela = build_contingency_table(observations)
    assert tabela.total == 3
    assert tabela.nao_classificados == 2
    assert any("2 trial(s) sem estratégia" in aviso for aviso in tabela.avisos)


def test_unknown_strategy_is_refused_not_dropped():
    with pytest.raises(ValueError, match="tigmotaxia"):
        build_contingency_table(_obs(1, serial=2) + [StrategyObservation(1, "tigmotaxia")])


def test_categories_are_a_parameter():
    tabela = build_contingency_table(_obs(1, a=1) + _obs(2, b=1), categorias=("a", "b", "c"))
    assert tabela.categorias == ("a", "b", "c")
    assert tabela.categorias_ausentes == ("c",)


def test_row_outside_given_rows_is_refused():
    with pytest.raises(ValueError, match="fora de 'linhas'"):
        build_contingency_table(_obs(5, serial=1), linhas=[1, 2])


def test_repeated_categories_or_rows_are_refused():
    with pytest.raises(ValueError, match="sem repetição"):
        build_contingency_table([], categorias=("a", "a"))
    with pytest.raises(ValueError, match="repetidas"):
        build_contingency_table([], linhas=[1, 1])


# --- Seleção do teste (SCRUM-267, SCRUM-268, SCRUM-272) -----------------------------------


def test_scenario_1_large_sample_uses_chi_square_with_justification():
    tabela = build_contingency_table(_large_sample())
    result = run_independence_test(tabela, frequencia_esperada_minima=LIMIAR)
    expected = stats.chi2_contingency(np.array(tabela.contagens))
    assert result.teste is AppliedTest.QUI_QUADRADO
    assert result.nome_estatistica == "qui2"
    assert result.estatistica == pytest.approx(expected.statistic)
    assert result.valor_p == pytest.approx(expected.pvalue)
    assert result.graus_liberdade == 6
    assert result.celulas_abaixo_do_limiar == 0
    assert result.menor_frequencia_esperada >= LIMIAR
    assert result.correcao_continuidade is False  # Yates só atua com 1 grau de liberdade
    assert "Qui-quadrado" in result.justificativa
    assert ">= 5" in result.justificativa


def test_chi_square_2x2_records_yates_correction():
    tabela = build_contingency_table(
        _obs("WT", spatial=20, random=10) + _obs("mutante", spatial=8, random=22),
        categorias=("spatial", "random"),
        linhas=["WT", "mutante"],
        dimensao="grupo",
    )
    result = run_independence_test(tabela, frequencia_esperada_minima=LIMIAR)
    expected = stats.chi2_contingency(np.array([[20, 10], [8, 22]]), correction=True)
    assert result.teste is AppliedTest.QUI_QUADRADO
    assert result.correcao_continuidade is True
    assert result.valor_p == pytest.approx(expected.pvalue)
    assert "Yates" in result.justificativa


def test_scenario_2_small_2x2_uses_exact_fisher_and_says_why():
    tabela = build_contingency_table(
        _obs(1, spatial=1, random=6) + _obs(4, spatial=5, random=1),
        categorias=("spatial", "random"),
    )
    result = run_independence_test(tabela, frequencia_esperada_minima=LIMIAR)
    expected = stats.fisher_exact([[1, 6], [5, 1]])
    assert result.teste is AppliedTest.FISHER_EXATO_2X2
    assert result.nome_estatistica == "razao_de_chances"
    assert result.estatistica == pytest.approx(expected.statistic)
    assert result.valor_p == pytest.approx(expected.pvalue)
    assert result.celulas_abaixo_do_limiar > 0
    assert result.monte_carlo is None
    assert "abaixo de 5" in result.justificativa
    assert "trocado pelo exato de Fisher" in result.justificativa


def test_scenario_2_small_rxc_uses_monte_carlo_fisher_reproducibly():
    observations = _obs(1, spatial=0, serial=3, random=6) + _obs(4, spatial=7, serial=2, random=0)
    tabela = build_contingency_table(observations)
    first = run_independence_test(tabela, frequencia_esperada_minima=LIMIAR)
    second = run_independence_test(tabela, frequencia_esperada_minima=LIMIAR)
    assert first.teste is AppliedTest.FISHER_MONTE_CARLO
    assert first.nome_estatistica == "probabilidade_da_tabela"
    assert first.monte_carlo == {
        "reamostragens": MONTE_CARLO_REAMOSTRAGENS,
        "semente": MONTE_CARLO_SEMENTE,
    }
    assert first.valor_p == second.valor_p  # semente fixa: mesmo dado, mesmo valor-p
    assert 0 < first.valor_p < 0.01  # padrões opostos nas duas sessões
    assert any("Monte Carlo" in aviso for aviso in first.avisos)


def test_monte_carlo_matches_exact_enumeration_on_a_tiny_table():
    """O valor-p de Monte Carlo converge para o exato (enumeração completa, 2×3)."""
    table = np.array([[3, 1, 0], [0, 2, 3]])
    tabela = build_contingency_table(
        _obs(1, a=3, b=1) + _obs(2, b=2, c=3), categorias=("a", "b", "c")
    )
    result = run_independence_test(tabela, frequencia_esperada_minima=LIMIAR)

    dist = stats.random_table(table.sum(axis=1), table.sum(axis=0))
    p_obs = dist.pmf(table)
    exact = 0.0
    n1 = table.sum(axis=1)[0]
    c1, c2, c3 = table.sum(axis=0)
    for a in range(min(n1, c1) + 1):
        for b in range(min(n1 - a, c2) + 1):
            c = n1 - a - b
            if c > c3:
                continue
            candidate = np.array([[a, b, c], [c1 - a, c2 - b, c3 - c]])
            p = dist.pmf(candidate)
            if p <= p_obs * (1 + 1e-7):
                exact += p
    assert result.estatistica == pytest.approx(p_obs)
    assert result.valor_p == pytest.approx(exact, abs=0.005)


def test_limit_changes_the_selected_test():
    tabela = build_contingency_table(_large_sample())
    menor = run_independence_test(tabela, frequencia_esperada_minima=LIMIAR)
    assert menor.teste is AppliedTest.QUI_QUADRADO
    strict = run_independence_test(
        tabela, frequencia_esperada_minima=menor.menor_frequencia_esperada + 1
    )
    assert strict.teste is AppliedTest.FISHER_MONTE_CARLO


def test_single_row_or_single_category_gives_no_test():
    tabela = build_contingency_table(_obs(1, serial=4, random=3))
    result = run_independence_test(tabela, frequencia_esperada_minima=LIMIAR)
    assert result.teste is None
    assert result.valor_p is None
    assert "Nenhum teste aplicado" in result.justificativa
    assert "Teste: **nenhum**" in render_markdown(result)


@pytest.mark.parametrize("bad", [0, -1, float("nan"), True])
def test_invalid_limit_is_refused(bad):
    tabela = build_contingency_table(_large_sample())
    with pytest.raises(ValueError):
        run_independence_test(tabela, frequencia_esperada_minima=bad)


# --- Grupo × estratégia (SCRUM-271) -------------------------------------------------------


def test_same_procedure_for_group_by_strategy():
    observations = _obs("WT", spatial=6, serial=2, random=1) + _obs(
        "mutante", spatial=1, serial=3, random=5
    )
    tabela = build_contingency_table(observations, linhas=["WT", "mutante"], dimensao="grupo")
    result = run_independence_test(tabela, frequencia_esperada_minima=LIMIAR)
    assert tabela.linhas == ("WT", "mutante")
    assert result.teste is AppliedTest.FISHER_MONTE_CARLO
    report = render_markdown(result)
    assert "grupo × estratégia" in report
    assert "| WT | 6 | 2 | 1 | 9 |" in report


def test_mixed_row_label_types_need_explicit_order():
    with pytest.raises(ValueError, match="'linhas'"):
        build_contingency_table(_obs(1, serial=1) + _obs("WT", serial=1))


# --- Relato (SCRUM-269) -------------------------------------------------------------------


def test_record_is_json_with_table_test_statistic_p_value_and_justification():
    tabela = build_contingency_table(_large_sample())
    record = run_independence_test(tabela, frequencia_esperada_minima=LIMIAR).as_record()
    text = json.dumps(record, ensure_ascii=False, allow_nan=False)
    loaded = json.loads(text)
    for key in ("tabela", "teste", "estatistica", "valor_p", "justificativa"):
        assert loaded[key] is not None
    assert loaded["teste"] == "qui_quadrado"
    assert loaded["limiar_frequencia_esperada"] == LIMIAR


def test_markdown_report_lists_table_and_result():
    result = run_independence_test(
        build_contingency_table(_large_sample()), frequencia_esperada_minima=LIMIAR
    )
    report = render_markdown(result)
    assert "| sessão | spatial | serial | random | total |" in report
    assert "| 1 | 2 | 8 | 20 | 30 |" in report
    assert "| **total** | 40 | 34 | 46 | 120 |" in report
    assert "valor-p" in report
    assert "Justificativa" in report


# --- Configuração (limiar null) -----------------------------------------------------------


def _config(tmp_path, body: str) -> Path:
    path = tmp_path / "default.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_production_config_leaves_the_limit_null_and_is_refused():
    with pytest.raises(StatsConfigError, match="vazio"):
        load_min_expected_frequency(REPO_ROOT / "configs" / "default.yaml")


def test_config_value_is_read(tmp_path):
    path = _config(tmp_path, "estatistica:\n  frequencia_esperada_minima: 5\n")
    assert load_min_expected_frequency(path) == 5.0


@pytest.mark.parametrize(
    "body",
    [
        "outra: 1\n",
        "estatistica:\n  frequencia_esperada_minima: cinco\n",
        "estatistica:\n  frequencia_esperada_minima: 0\n",
        "estatistica:\n  frequencia_esperada_minima: true\n",
    ],
)
def test_invalid_config_is_refused(tmp_path, body):
    with pytest.raises(StatsConfigError):
        load_min_expected_frequency(_config(tmp_path, body))


def test_missing_config_file_is_refused(tmp_path):
    with pytest.raises(StatsConfigError, match="não encontrado"):
        load_min_expected_frequency(tmp_path / "nao_existe.yaml")
