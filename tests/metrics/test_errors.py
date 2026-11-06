"""Contagem e sequência de erros (US-17): definição em configs/ e cálculo só sobre a sequência."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import barnes.metrics.errors as errors_module
from barnes.metrics.errors import (
    ErrorConfigError,
    ErrorCriterion,
    ErrorDefinition,
    TrialErrors,
    VisitItem,
    VisitSequence,
    compute_errors,
    load_error_definition,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
N_HOLES = 20
TARGET = 10
# 0,5 s é só o valor do Cenário 2 do card, usado nos testes; nunca vai para configs/.
DWELL_CENARIO_2 = 0.5

QUALQUER = ErrorDefinition(ErrorCriterion.QUALQUER_BURACO_INCORRETO)
ACIMA_05 = ErrorDefinition(ErrorCriterion.ACIMA_DE_DURACAO, DWELL_CENARIO_2)


def _item(hole: int, inicio_s: float, dwell_s: float | None = 1.0) -> VisitItem:
    return VisitItem(
        buraco_platform=hole,
        angulo_deg_room=hole * 360.0 / N_HOLES,
        inicio_s=inicio_s,
        dwell_s=dwell_s,
        alvo=hole == TARGET,
    )


# Cenários 1 e 2: 7 checagens, 6 em buracos incorretos (o 3 é revisitado), alvo na 5ª.
SETE_CHECAGENS = VisitSequence.avaliada(
    [
        _item(3, 4.0, 0.2),
        _item(5, 9.5, 0.8),
        _item(8, 15.0, 0.5),  # exatamente no limite do Cenário 2: conta (>=)
        _item(3, 22.0, 1.2),
        _item(TARGET, 30.0, 2.0),
        _item(11, 41.0, 0.3),
        _item(14, 50.0, 0.6),
    ]
)


def _config(tmp_path, body):
    path = tmp_path / "default.yaml"
    path.write_text(body, encoding="utf-8")
    return path


# --- Definição em configs/ (RN01, SCRUM-211) ----------------------------------------------


def test_production_config_keeps_c3_null_and_is_refused():
    # Até o laboratório responder C3, a definição de produção fica null e é recusada.
    with pytest.raises(ErrorConfigError, match=r"erro\.criterio.*C3"):
        load_error_definition(REPO_ROOT / "configs" / "default.yaml")


def test_null_criterion_is_refused_naming_the_key_and_c3(tmp_path):
    path = _config(tmp_path, "erro:\n  criterio: null\n  duracao_minima_s: null\n")
    with pytest.raises(ErrorConfigError, match=r"erro\.criterio.*C3"):
        load_error_definition(path)


def test_any_incorrect_hole_definition_is_read(tmp_path):
    path = _config(tmp_path, "erro:\n  criterio: qualquer_buraco_incorreto\n")
    definicao = load_error_definition(path)
    assert definicao == QUALQUER
    assert definicao.duracao_minima_s is None


def test_duration_definition_is_read(tmp_path):
    path = _config(tmp_path, "erro:\n  criterio: acima_de_duracao\n  duracao_minima_s: 0.5\n")
    assert load_error_definition(path) == ACIMA_05


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("trial: {}\n", "Seção 'erro'"),
        ("erro:\n  criterio: buraco_errado\n", "desconhecido"),
        ("erro:\n  criterio: 3\n", "desconhecido"),
        ("erro:\n  criterio: acima_de_duracao\n", r"erro\.duracao_minima_s.*C3"),
        ("erro:\n  criterio: acima_de_duracao\n  duracao_minima_s: 0\n", "maior que zero"),
        ("erro:\n  criterio: acima_de_duracao\n  duracao_minima_s: -1\n", "maior que zero"),
        ("erro:\n  criterio: acima_de_duracao\n  duracao_minima_s: meio\n", "maior que zero"),
        ("erro:\n  criterio: acima_de_duracao\n  duracao_minima_s: true\n", "maior que zero"),
        ("erro:\n  criterio: acima_de_duracao\n  duracao_minima_s: .inf\n", "maior que zero"),
        (
            "erro:\n  criterio: qualquer_buraco_incorreto\n  duracao_minima_s: 0.5\n",
            "não se aplica",
        ),
    ],
)
def test_invalid_definition_is_refused(tmp_path, body, message):
    with pytest.raises(ErrorConfigError, match=message):
        load_error_definition(_config(tmp_path, body))


def test_missing_config_file_is_refused():
    with pytest.raises(ErrorConfigError, match="não encontrado"):
        load_error_definition("nao-existe.yaml")


# --- Entrada: sequência de visitação (contrato mínimo da US-15) -------------------------


def test_sequence_states_are_distinct():
    vazia = VisitSequence.avaliada([])
    ausente = VisitSequence.nao_avaliada()
    assert vazia.disponivel and vazia.itens == ()
    assert not ausente.disponivel
    assert vazia != ausente


def test_unordered_sequence_is_refused_not_sorted():
    with pytest.raises(ValueError, match="ordem cronológica"):
        VisitSequence.avaliada([_item(3, 10.0), _item(5, 4.0)])
    with pytest.raises(ValueError, match="ordem cronológica"):
        VisitSequence.avaliada([_item(3, 10.0), _item(5, 10.0)])


def test_inconsistent_target_marks_are_refused():
    outro_alvo = VisitItem(4, 72.0, 12.0, 1.0, alvo=True)
    with pytest.raises(ValueError, match="Mais de um buraco"):
        VisitSequence.avaliada([_item(TARGET, 5.0), outro_alvo])
    alvo_sem_marca = VisitItem(TARGET, 180.0, 12.0, 1.0, alvo=False)
    with pytest.raises(ValueError, match="alvo e como não alvo"):
        VisitSequence.avaliada([_item(TARGET, 5.0), alvo_sem_marca])


def test_not_evaluated_sequence_cannot_have_items():
    with pytest.raises(ValueError, match="não avaliada"):
        VisitSequence(disponivel=False, itens=(_item(3, 1.0),))


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"buraco_platform": -1}, "buraco_platform"),
        ({"buraco_platform": True}, "buraco_platform"),
        ({"angulo_deg_room": 360.0}, "angulo_deg_room"),
        ({"angulo_deg_room": float("nan")}, "angulo_deg_room"),
        ({"inicio_s": -0.1}, "RN04"),
        ({"inicio_s": float("inf")}, "inicio_s"),
        ({"dwell_s": -0.1}, "dwell_s"),
        ({"dwell_s": float("nan")}, "dwell_s"),
    ],
)
def test_invalid_visit_item_is_refused(kwargs, message):
    base = {
        "buraco_platform": 3,
        "angulo_deg_room": 54.0,
        "inicio_s": 1.0,
        "dwell_s": 0.4,
        "alvo": False,
    }
    with pytest.raises(ValueError, match=message):
        VisitItem(**(base | kwargs))


def test_non_boolean_target_flag_is_refused():
    with pytest.raises(TypeError, match="alvo"):
        VisitItem(3, 54.0, 1.0, 0.4, alvo=1)


# --- Contagem, sequência e erros até o alvo (SCRUM-212/213/214) -------------------------


def test_scenario_1_any_incorrect_hole_counts_six_in_order():
    resultado = compute_errors(SETE_CHECAGENS, QUALQUER)
    assert resultado.total == 6
    assert resultado.buracos_platform == (3, 5, 8, 3, 11, 14)  # ordem cronológica, revisita conta
    assert resultado.angulos_deg_room == (54.0, 90.0, 144.0, 54.0, 198.0, 252.0)
    assert [item.inicio_s for item in resultado.sequencia] == [4.0, 9.5, 15.0, 22.0, 41.0, 50.0]
    assert resultado.ate_alvo == 4  # os quatro antes da primeira checagem do alvo (30 s)
    assert resultado.primary_censurado is False
    assert resultado.as_trial_results() == {"primary_errors": 4, "total_errors": 6}
    assert resultado.avisos == ()


def test_scenario_2_minimum_dwell_counts_the_subset():
    todos = compute_errors(SETE_CHECAGENS, QUALQUER)
    resultado = compute_errors(SETE_CHECAGENS, ACIMA_05)
    # dwell >= 0,5 s: 5 (0,8), 8 (0,5 — limite inclusivo), 3 (1,2), 14 (0,6).
    assert resultado.buracos_platform == (5, 8, 3, 14)
    assert resultado.total == 4
    assert resultado.ate_alvo == 3
    assert set(resultado.sequencia) <= set(todos.sequencia)
    assert resultado.total < todos.total


def test_target_checks_are_never_errors_whatever_the_dwell():
    seq = VisitSequence.avaliada([_item(TARGET, 2.0, 5.0), _item(TARGET, 8.0, 0.1)])
    for definicao in (QUALQUER, ACIMA_05):
        resultado = compute_errors(seq, definicao)
        assert resultado.total == 0
        assert resultado.ate_alvo == 0
        assert resultado.sequencia == ()


def test_errors_until_target_cut_at_first_target_check():
    seq = VisitSequence.avaliada(
        [
            _item(2, 1.0),
            _item(TARGET, 3.0),
            _item(4, 6.0),
            _item(TARGET, 9.0),
            _item(6, 12.0),
        ]
    )
    resultado = compute_errors(seq, QUALQUER)
    assert resultado.ate_alvo == 1
    assert resultado.total == 3
    assert resultado.primary_censurado is False


def test_target_first_means_zero_errors_until_target():
    seq = VisitSequence.avaliada([_item(TARGET, 1.0), _item(2, 5.0)])
    resultado = compute_errors(seq, QUALQUER)
    assert resultado.as_trial_results() == {"primary_errors": 0, "total_errors": 1}


def test_target_never_checked_keeps_all_errors_censored_not_zero():
    seq = VisitSequence.avaliada([_item(1, 1.0), _item(2, 5.0), _item(1, 9.0)])
    resultado = compute_errors(seq, QUALQUER)
    assert resultado.total == 3
    assert resultado.ate_alvo == 3
    assert resultado.primary_censurado is True
    assert any("censurado" in aviso for aviso in resultado.avisos)


def test_empty_evaluated_sequence_is_zero_errors():
    resultado = compute_errors(VisitSequence.avaliada([]), QUALQUER)
    assert resultado.calculado
    assert resultado.total == 0
    assert resultado.sequencia == ()
    assert resultado.primary_censurado is True  # nenhuma checagem, nem do alvo


def test_missing_sequence_is_not_calculated_not_zero():
    resultado = compute_errors(VisitSequence.nao_avaliada(), QUALQUER)
    assert not resultado.calculado
    assert resultado.sequencia is None
    assert resultado.buracos_platform is None
    assert resultado.angulos_deg_room is None
    assert resultado.primary_censurado is None
    assert resultado.as_trial_results() == {"primary_errors": None, "total_errors": None}
    assert any("US-15" in aviso for aviso in resultado.avisos)


def test_duration_criterion_without_dwell_is_not_calculated():
    seq = VisitSequence.avaliada([_item(3, 1.0, 0.9), _item(5, 4.0, None), _item(TARGET, 8.0)])
    resultado = compute_errors(seq, ACIMA_05)
    assert not resultado.calculado
    assert resultado.as_trial_results() == {"primary_errors": None, "total_errors": None}
    assert any("US-14" in aviso and "4 s" in aviso for aviso in resultado.avisos)


def test_missing_dwell_does_not_matter_for_any_incorrect_hole_or_target():
    seq = VisitSequence.avaliada([_item(3, 1.0, None), _item(TARGET, 4.0, None)])
    assert compute_errors(seq, QUALQUER).total == 1
    # Sob duração mínima, só checagens incorretas precisam de dwell; aqui falta só no alvo.
    seq_alvo_sem_dwell = VisitSequence.avaliada([_item(3, 1.0, 0.7), _item(TARGET, 4.0, None)])
    assert compute_errors(seq_alvo_sem_dwell, ACIMA_05).total == 1


def test_result_records_the_definition_used():
    resultado = compute_errors(SETE_CHECAGENS, ACIMA_05)
    assert isinstance(resultado, TrialErrors)
    assert resultado.definicao == ACIMA_05
    assert "0.5 s" in resultado.definicao.descricao()


# --- Recálculo sob nova definição sem vídeo nem trajetória (RN05, SCRUM-215) ------------


def test_recalculation_under_new_definition_never_touches_video_or_trajectory(
    tmp_path, monkeypatch
):
    import cv2
    import pyarrow.parquet as pq

    from barnes.io import video
    from barnes.pose import trajectory

    def proibido(*_args, **_kwargs):
        raise AssertionError("US-17 RN05: o recálculo de erros não pode abrir vídeo/trajetória.")

    monkeypatch.setattr(cv2, "VideoCapture", proibido)
    monkeypatch.setattr(pq, "read_table", proibido)
    for nome in ("load_trial_video", "read_frame", "iter_frames"):
        monkeypatch.setattr(video, nome, proibido)
    monkeypatch.setattr(trajectory, "read_trajectory", proibido)

    antes = load_error_definition(
        _config(tmp_path, "erro:\n  criterio: qualquer_buraco_incorreto\n")
    )
    primeira = compute_errors(SETE_CHECAGENS, antes)

    depois_path = tmp_path / "revisada.yaml"
    depois_path.write_text(
        "erro:\n  criterio: acima_de_duracao\n  duracao_minima_s: 0.5\n", encoding="utf-8"
    )
    segunda = compute_errors(SETE_CHECAGENS, load_error_definition(depois_path))

    assert (primeira.total, segunda.total) == (6, 4)
    assert (primeira.ate_alvo, segunda.ate_alvo) == (4, 3)


def test_errors_module_depends_only_on_the_sequence():
    # RN02: nada de vídeo, trajetória, pose, eventos ou banco no módulo de erros.
    tree = ast.parse(Path(errors_module.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    proibidos = ("cv2", "pyarrow", "numpy", "psycopg", "barnes.io", "barnes.pose", "barnes.db")
    proibidos += ("barnes.events",)
    assert not [m for m in imported if m.startswith(proibidos)], imported
