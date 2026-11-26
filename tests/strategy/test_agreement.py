"""Kappa de Cohen, partição e rodadas da US-21, com rótulos sintéticos.

Rótulos sintéticos provam o ferramental; não são validação real da regra da US-20
(não há observador — `docs/decisoes-sem-laboratorio.md` §5.1).
"""

from __future__ import annotations

import pytest

from barnes.strategy.agreement import (
    CATEGORIES,
    KAPPA_THRESHOLD,
    AgreementError,
    ManualLabel,
    ManualLabelError,
    PartitionError,
    StrategyPair,
    blocked_record,
    compute_agreement,
    load_manual_labels,
    load_partition,
    optimism_warning,
    parse_strategy_label,
    render_history,
    render_markdown,
    split_sample,
    write_partition,
)
from barnes.strategy.classification import SearchStrategy

SP, SE, RA = SearchStrategy.SPATIAL, SearchStrategy.SERIAL, SearchStrategy.RANDOM
MANUAL = [SP] * 4 + [SE] * 3 + [RA] * 3


def _pairs(auto):
    return [StrategyPair(i + 1, m, a) for i, (m, a) in enumerate(zip(MANUAL, auto, strict=True))]


def _labels(categories):
    return [ManualLabel(i + 1, c, "obs", "2026-11-25") for i, c in enumerate(categories)]


def test_scenario1_high_agreement_is_approved_with_ordered_confusion_matrix():
    auto = [SP] * 4 + [SE] * 3 + [RA, RA, SP]
    result = compute_agreement(_pairs(auto), subconjunto="avaliacao")

    assert result.kappa == pytest.approx(0.8462, abs=1e-4)
    assert result.kappa >= KAPPA_THRESHOLD
    assert result.aprovado
    assert result.categorias == ("spatial", "serial", "random")
    # linha = observador, coluna = regra
    assert result.matriz == ((4, 0, 0), (0, 3, 0), (1, 0, 2))
    assert result.concordancia_bruta == pytest.approx(0.9)
    random = result.por_categoria[2]
    assert (random.n_manual, random.n_automatico, random.acertos) == (3, 2, 2)
    assert random.sensibilidade == pytest.approx(2 / 3)
    assert random.precisao == pytest.approx(1.0)
    assert result.as_record()["status"] == "aprovado"


def test_scenario2_low_agreement_is_rejected():
    auto = [SP, SP, SP, RA] + [SE, SE, RA] + [RA, RA, SP]
    result = compute_agreement(_pairs(auto), subconjunto="calibracao")

    assert result.kappa == pytest.approx(0.5455, abs=1e-4)
    assert not result.aprovado
    record = result.as_record()
    assert record["status"] == "reprovado"
    assert "não é o resultado final" in record["declaracao"]


def test_scenario3_evaluation_round_declares_trials_were_not_used_for_tuning():
    record = compute_agreement(_pairs(MANUAL), subconjunto="avaliacao").as_record()
    assert "não participaram do ajuste" in record["declaracao"]
    assert "10 trials" in record["declaracao"]
    assert record["declaracao"] in render_markdown(record)


def test_scenario3_partition_is_stratified_disjoint_and_deterministic():
    labels = _labels([SP] * 10 + [SE] * 10 + [RA] * 10)
    a = split_sample(labels, frac_avaliacao=0.3, seed=21, manual_sha256="x")
    b = split_sample(labels, frac_avaliacao=0.3, seed=21, manual_sha256="x")
    c = split_sample(labels, frac_avaliacao=0.3, seed=22, manual_sha256="x")

    assert a == b
    assert a.avaliacao != c.avaliacao
    assert not set(a.calibracao) & set(a.avaliacao)
    assert set(a.calibracao) | set(a.avaliacao) == set(range(1, 31))
    by_id = {label.trial_id: label.estrategia for label in labels}
    for categoria in CATEGORIES:
        assert sum(by_id[t] == categoria for t in a.avaliacao) == 3


def test_partition_round_trip_refuses_overwrite_and_other_annotation(tmp_path):
    partition = split_sample(_labels(MANUAL), frac_avaliacao=0.3, seed=1, manual_sha256="abc")
    path = write_partition(tmp_path / "particao.json", partition)

    assert load_partition(path, manual_sha256="abc") == partition
    with pytest.raises(PartitionError, match="Já existe"):
        write_partition(path, partition)
    with pytest.raises(PartitionError, match="outro CSV"):
        load_partition(path, manual_sha256="def")
    with pytest.raises(PartitionError, match="strategy split"):
        load_partition(tmp_path / "nao-existe.json", manual_sha256="abc")


def test_partition_needs_both_sides_and_valid_fraction():
    with pytest.raises(PartitionError, match="ao menos um trial"):
        split_sample(_labels([SP, SE]), frac_avaliacao=0.1, seed=1, manual_sha256="x")
    with pytest.raises(PartitionError, match="entre 0 e 1"):
        split_sample(_labels(MANUAL), frac_avaliacao=1.0, seed=1, manual_sha256="x")


def test_absent_category_stays_as_zeros_and_is_flagged():
    pairs = [StrategyPair(i, m, m) for i, m in enumerate([SP, SP, SE, SE], start=1)]
    result = compute_agreement(pairs, subconjunto="avaliacao")
    assert result.kappa == pytest.approx(1.0)
    assert result.matriz[2] == (0, 0, 0)
    assert result.categorias_ausentes == ("random",)
    assert result.por_categoria[2].sensibilidade is None


def test_single_shared_category_makes_kappa_undefined_not_a_number():
    pairs = [StrategyPair(i, SP, SP) for i in range(1, 5)]
    with pytest.raises(AgreementError, match="Kappa indefinido"):
        compute_agreement(pairs, subconjunto="avaliacao")


def test_too_few_pairs_and_invalid_subset_are_refused():
    with pytest.raises(AgreementError, match="ao menos 3"):
        compute_agreement(_pairs(MANUAL)[:2], subconjunto="avaliacao")
    with pytest.raises(AgreementError, match="inválido"):
        compute_agreement(_pairs(MANUAL), subconjunto="teste")


@pytest.mark.parametrize(
    ("text", "expected"),
    [("Espacial", SP), ("spatial", SP), (" serial ", SE), ("aleatória", RA), ("RANDOM", RA)],
)
def test_labels_accept_portuguese_and_english(text, expected):
    assert parse_strategy_label(text) is expected


def test_load_manual_labels_validates_format(tmp_path):
    good = tmp_path / "rotulos.csv"
    good.write_text(
        "trial_id,estrategia_manual,observador,data\n1,espacial,A,2026-11-25\n2,serial,A,\n",
        encoding="utf-8",
    )
    labels = load_manual_labels(good)
    assert [(lb.trial_id, lb.estrategia) for lb in labels] == [(1, SP), (2, SE)]

    cases = {
        "trial_id,observador,data\n1,A,x\n": "faltam as colunas estrategia_manual",
        "trial_id,estrategia_manual,observador,data\n1,espacial,A,x\n1,serial,A,x\n": "repetido",
        "trial_id,estrategia_manual,observador,data\nx,espacial,A,x\n": "não inteiro",
        "trial_id,estrategia_manual,observador,data\n1,tigmotaxia,A,x\n": "desconhecida",
        "trial_id,estrategia_manual,observador,data\n": "nenhum rótulo",
    }
    for content, message in cases.items():
        bad = tmp_path / "ruim.csv"
        bad.write_text(content, encoding="utf-8")
        with pytest.raises(ManualLabelError, match=message):
            load_manual_labels(bad)
    with pytest.raises(ManualLabelError, match="não encontrados"):
        load_manual_labels(tmp_path / "nao-existe.csv")


def test_blocked_record_renders_without_numbers():
    record = blocked_record("rótulos manuais não entregues")
    text = render_markdown(record)
    assert record["status"] == "bloqueado"
    assert "kappa = " not in text
    assert "Próxima ação" in text


def test_cli_without_manual_labels_records_blocked_round(tmp_path):
    # Não toca o banco: sem rótulos, a rodada é bloqueada antes de conectar.
    import json

    from typer.testing import CliRunner

    from barnes import cli

    saida = tmp_path / "rodadas"
    result = CliRunner().invoke(
        cli.app, ["strategy", "agreement", "--subconjunto", "avaliacao", "--saida", str(saida)]
    )
    assert result.exit_code == 2, result.output
    assert "Bloqueado" in result.output
    record = json.loads(next(saida.glob("agreement-*/rodada.json")).read_text(encoding="utf-8"))
    assert record["status"] == "bloqueado"
    assert record["subconjunto"] == "avaliacao"
    assert "kappa" not in record

    history = CliRunner().invoke(cli.app, ["strategy", "agreement-history", "--saida", str(saida)])
    assert history.exit_code == 0
    assert "bloqueado" in history.output


def test_reevaluating_evaluation_subset_with_other_thresholds_warns():
    first = compute_agreement(_pairs(MANUAL), subconjunto="avaliacao").as_record() | {
        "limiares": {"erros_ate_alvo_max": 3},
        "criado_em": "2026-11-25T10:00:00+00:00",
    }
    calibration = first | {"subconjunto": "calibracao", "limiares": {"erros_ate_alvo_max": 1}}

    assert optimism_warning([first], limiares={"erros_ate_alvo_max": 3}) is None
    assert optimism_warning([calibration], limiares={"erros_ate_alvo_max": 2}) is None
    warning = optimism_warning([first, calibration], limiares={"erros_ate_alvo_max": 2})
    assert warning is not None and "otimista" in warning
    assert optimism_warning([blocked_record("x", subconjunto="avaliacao")], limiares={}) is None

    second = first | {"aviso_otimismo": warning, "criado_em": "2026-11-26T10:00:00+00:00"}
    lines = render_history([second, first])
    assert lines[0].startswith("  1. 2026-11-25")
    assert any("aviso:" in line for line in lines)
