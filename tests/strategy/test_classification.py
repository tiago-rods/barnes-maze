"""Regra de classificação de estratégia (US-20): cálculo puro, sem banco nem vídeo."""

from __future__ import annotations

from pathlib import Path

import pytest

from barnes.metrics.errors import ErrorCriterion, ErrorDefinition, TrialErrors
from barnes.strategy.classification import (
    ClassificationError,
    SearchStrategy,
    StrategyConfigError,
    StrategyThresholds,
    classify_strategy,
    load_strategy_thresholds,
)
from barnes.strategy.signals import AngularAdjacency, CenterCrossings

DEFINICAO = ErrorDefinition(criterio=ErrorCriterion.QUALQUER_BURACO_INCORRETO)

DEFAULT_THRESHOLDS = StrategyThresholds(
    cruzamentos_centro_min=1,
    adjacencia_angular_graus=18.0,
    erros_ate_alvo_max=3,
    centro_zona_raio_frac=0.5,
    serial_min_buracos=2,
)


def _crossings(n: int | None) -> CenterCrossings:
    return CenterCrossings(
        cruzamentos=n, zona_raio_cm=40.0, n_amostras=100, ponto="centro_corpo", until_s=5.0, avisos=()
    )


def _adjacency(
    *, primeiro: float | None, maior: int, censurado: bool = False
) -> AngularAdjacency:
    return AngularAdjacency(
        buracos_platform=(),
        primeiro_buraco_distancia_deg=primeiro,
        maior_sequencia_buracos=maior,
        primary_censurado=censurado,
        avisos=(),
    )


def _errors(*, ate_alvo: int | None, total: int | None = None, censurado: bool = False) -> TrialErrors:
    return TrialErrors(
        definicao=DEFINICAO,
        sequencia=(),
        total=ate_alvo if total is None else total,
        ate_alvo=ate_alvo,
        primary_censurado=censurado if ate_alvo is not None else None,
        avisos=(),
    )


# --- classify_strategy: cenários do card ----------------------------------------


def test_cenario_1_serial():
    """Buracos angularmente adjacentes em sequência, sem cruzar o centro."""
    result = classify_strategy(
        _crossings(0),
        _adjacency(primeiro=90.0, maior=3),
        _errors(ate_alvo=3),
        thresholds=DEFAULT_THRESHOLDS,
    )
    assert result.categoria is SearchStrategy.SERIAL
    assert result.calculado


def test_cenario_2_espacial_sem_cruzar_o_centro():
    """Direto ao alvo (ou buraco vizinho), poucos erros, SEM cruzar o centro.

    O Cenário 2 de docs/CARDS.md descreve o trial espacial "cruzando o
    centro" — redação em desacordo com Harrison et al. (2006), que define
    cruzar o centro como a assinatura da busca ALEATÓRIA (ver
    docs/definicoes-metricas.md). Este teste segue a literatura citada: 0
    cruzamentos para a classificação espacial.
    """
    result = classify_strategy(
        _crossings(0),
        _adjacency(primeiro=10.0, maior=1),
        _errors(ate_alvo=1),
        thresholds=DEFAULT_THRESHOLDS,
    )
    assert result.categoria is SearchStrategy.SPATIAL


def test_cenario_3_aleatoria_entropia_alta_e_sinais_registrados():
    """Muitos cruzamentos, buracos sem adjacência, muitos erros -> aleatória."""
    result = classify_strategy(
        _crossings(5),
        _adjacency(primeiro=170.0, maior=1),
        _errors(ate_alvo=8),
        thresholds=DEFAULT_THRESHOLDS,
    )
    assert result.categoria is SearchStrategy.RANDOM
    # RN06: os três sinais ficam auditáveis caso a caso.
    sinais = result.sinais_auditoria()
    assert sinais == {
        "cruzamentos_centro": 5,
        "primeiro_buraco_distancia_deg": 170.0,
        "maior_sequencia_buracos_adjacentes": 1,
        "erros_ate_alvo": 8,
        "primary_censurado": False,
    }


def test_cenario_4_ajuste_de_limiar_sem_alteracao_de_codigo():
    """O mesmo trial muda de categoria só por reexecutar com outro `erros_ate_alvo_max`."""
    crossings, adjacency, errors = _crossings(0), _adjacency(primeiro=10.0, maior=1), _errors(ate_alvo=4)

    com_limiar_padrao = classify_strategy(crossings, adjacency, errors, thresholds=DEFAULT_THRESHOLDS)
    assert com_limiar_padrao.categoria is SearchStrategy.RANDOM  # 4 erros > erros_ate_alvo_max=3

    limiar_ajustado = StrategyThresholds(
        cruzamentos_centro_min=1,
        adjacencia_angular_graus=18.0,
        erros_ate_alvo_max=5,  # único valor alterado, via YAML na prática
        centro_zona_raio_frac=0.5,
        serial_min_buracos=2,
    )
    com_limiar_ajustado = classify_strategy(crossings, adjacency, errors, thresholds=limiar_ajustado)
    assert com_limiar_ajustado.categoria is SearchStrategy.SPATIAL


# --- Casos "não classificado" (nunca confundidos com aleatória) -----------------


def test_sem_cruzamentos_calculados_nao_classifica():
    result = classify_strategy(
        _crossings(None), _adjacency(primeiro=10.0, maior=1), _errors(ate_alvo=1), thresholds=DEFAULT_THRESHOLDS
    )
    assert result.categoria is None
    assert not result.calculado
    assert any("cruzamentos do centro não calculados" in aviso for aviso in result.avisos)


def test_sem_erros_calculados_nao_classifica():
    result = classify_strategy(
        _crossings(0), _adjacency(primeiro=10.0, maior=1), _errors(ate_alvo=None), thresholds=DEFAULT_THRESHOLDS
    )
    assert result.categoria is None
    assert any("erros até o alvo não calculados" in aviso for aviso in result.avisos)


def test_censura_divergente_entre_sinais_recusada():
    with pytest.raises(ClassificationError, match="censura"):
        classify_strategy(
            _crossings(0),
            _adjacency(primeiro=None, maior=0, censurado=True),
            _errors(ate_alvo=2, censurado=False),
            thresholds=DEFAULT_THRESHOLDS,
        )


def test_as_trial_results_none_quando_nao_classificado():
    result = classify_strategy(
        _crossings(None), _adjacency(primeiro=None, maior=0), _errors(ate_alvo=0), thresholds=DEFAULT_THRESHOLDS
    )
    assert result.as_trial_results() == {"search_strategy": None}


def test_as_trial_results_valor_do_banco():
    result = classify_strategy(
        _crossings(0), _adjacency(primeiro=10.0, maior=1), _errors(ate_alvo=1), thresholds=DEFAULT_THRESHOLDS
    )
    assert result.as_trial_results() == {"search_strategy": "spatial"}


# --- StrategyThresholds: validação -----------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"cruzamentos_centro_min": -1},
        {"adjacencia_angular_graus": 200.0},
        {"erros_ate_alvo_max": -1},
        {"centro_zona_raio_frac": 0.0},
        {"centro_zona_raio_frac": 1.0},
        {"serial_min_buracos": 1},
    ],
)
def test_thresholds_invalidos_recusados(overrides):
    base = {
        "cruzamentos_centro_min": 1,
        "adjacencia_angular_graus": 18.0,
        "erros_ate_alvo_max": 3,
        "centro_zona_raio_frac": 0.5,
        "serial_min_buracos": 2,
    }
    with pytest.raises(StrategyConfigError):
        StrategyThresholds(**{**base, **overrides})


# --- load_strategy_thresholds ----------------------------------------------------


def test_le_limiares_do_arquivo_real_do_projeto():
    thresholds = load_strategy_thresholds(Path("configs/default.yaml"))
    assert thresholds.cruzamentos_centro_min == 1
    assert thresholds.adjacencia_angular_graus == 18.0
    assert thresholds.erros_ate_alvo_max == 3
    assert thresholds.centro_zona_raio_frac == 0.5
    assert thresholds.serial_min_buracos == 2


def test_arquivo_ausente_recusado(tmp_path):
    with pytest.raises(StrategyConfigError, match="não encontrado"):
        load_strategy_thresholds(tmp_path / "nao-existe.yaml")


def test_secao_ausente_recusada(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("outra_secao: {}\n", encoding="utf-8")
    with pytest.raises(StrategyConfigError, match="'estrategia' ausente"):
        load_strategy_thresholds(config)


def test_chave_ausente_recusada(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        "estrategia:\n"
        "  cruzamentos_centro_min: 1\n"
        "  adjacencia_angular_graus: 18\n"
        "  erros_ate_alvo_max: 3\n"
        "  centro_zona_raio_frac: 0.5\n",
        encoding="utf-8",
    )
    with pytest.raises(StrategyConfigError, match="serial_min_buracos"):
        load_strategy_thresholds(config)
