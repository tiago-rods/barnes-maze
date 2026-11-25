"""Sinais de cruzamento do centro e adjacência angular (US-20): cálculo puro."""

from __future__ import annotations

import numpy as np
import pyarrow as pa
import pytest

from barnes.geometry.holes import generate_holes
from barnes.metrics.errors import VisitItem, VisitSequence
from barnes.strategy.signals import (
    SignalError,
    compute_angular_adjacency,
    count_center_crossings,
)

CM_PER_PX = 0.5
FPS = 25.0
STEP_S = 1.0 / FPS

GEOMETRY = generate_holes(
    center_x_px=200.0,
    center_y_px=200.0,
    platform_radius_px=160.0,
    hole_count=8,
    start_angle_deg=0.0,
    target_hole_number=0,
    hole_radius_px=8.0,
)
CENTER_CM = (200.0 * CM_PER_PX, 200.0 * CM_PER_PX)
RADIUS_CM = 80.0
ZONA_FRAC = 0.5
ZONA_RAIO_CM = RADIUS_CM * ZONA_FRAC

TARGET_ANGLE = 0.0
ADJ_GRAUS = 18.0


# --- count_center_crossings -----------------------------------------------------


def _table(points) -> pa.Table:
    xy = np.asarray(points, dtype=float)
    n = len(xy)
    valid = np.ones(n, dtype=bool)
    return pa.table(
        {
            "t_s": np.arange(n) * STEP_S,
            "centro_corpo_x_cm_image": xy[:, 0],
            "centro_corpo_y_cm_image": xy[:, 1],
            "centro_corpo_valido": valid,
        }
    )


def _on_border(radius_cm: float) -> tuple[float, float]:
    return (CENTER_CM[0] + radius_cm, CENTER_CM[1])


def test_sem_cruzamento_fora_da_zona():
    pontos = [_on_border(RADIUS_CM)] * 10
    result = count_center_crossings(_table(pontos), GEOMETRY, CM_PER_PX, zona_raio_frac=ZONA_FRAC)
    assert result.calculado
    assert result.cruzamentos == 0


def test_uma_entrada_conta_um_cruzamento():
    pontos = [_on_border(RADIUS_CM)] * 5 + [CENTER_CM] * 5 + [_on_border(RADIUS_CM)] * 5
    result = count_center_crossings(_table(pontos), GEOMETRY, CM_PER_PX, zona_raio_frac=ZONA_FRAC)
    assert result.cruzamentos == 1


def test_entra_sai_entra_conta_dois_cruzamentos():
    dentro, fora = CENTER_CM, _on_border(RADIUS_CM)
    pontos = [fora] * 3 + [dentro] * 3 + [fora] * 3 + [dentro] * 3 + [fora] * 3
    result = count_center_crossings(_table(pontos), GEOMETRY, CM_PER_PX, zona_raio_frac=ZONA_FRAC)
    assert result.cruzamentos == 2


def test_comecar_dentro_nao_conta_mas_avisa():
    pontos = [CENTER_CM] * 5 + [_on_border(RADIUS_CM)] * 5
    result = count_center_crossings(_table(pontos), GEOMETRY, CM_PER_PX, zona_raio_frac=ZONA_FRAC)
    assert result.cruzamentos == 0
    assert any("já está dentro" in aviso for aviso in result.avisos)


def test_until_s_corta_cruzamento_posterior():
    pontos = [_on_border(RADIUS_CM)] * 5 + [CENTER_CM] * 5
    table = _table(pontos)
    until_s = float(table.column("t_s")[4].as_py())
    result = count_center_crossings(
        table, GEOMETRY, CM_PER_PX, zona_raio_frac=ZONA_FRAC, until_s=until_s
    )
    assert result.cruzamentos == 0
    assert result.n_amostras == 5


def test_sem_amostra_valida_cruzamentos_none():
    table = pa.table(
        {
            "t_s": np.array([0.0, 0.04]),
            "centro_corpo_x_cm_image": np.array([np.nan, np.nan]),
            "centro_corpo_y_cm_image": np.array([np.nan, np.nan]),
            "centro_corpo_valido": np.array([False, False]),
        }
    )
    result = count_center_crossings(table, GEOMETRY, CM_PER_PX, zona_raio_frac=ZONA_FRAC)
    assert not result.calculado
    assert result.cruzamentos is None


def test_zona_raio_frac_invalida_recusada():
    pontos = [_on_border(RADIUS_CM)] * 3
    with pytest.raises(SignalError, match="zona_raio_frac"):
        count_center_crossings(_table(pontos), GEOMETRY, CM_PER_PX, zona_raio_frac=1.5)


def test_zona_raio_cm_auditavel():
    pontos = [_on_border(RADIUS_CM)] * 3
    result = count_center_crossings(_table(pontos), GEOMETRY, CM_PER_PX, zona_raio_frac=ZONA_FRAC)
    assert result.zona_raio_cm == pytest.approx(ZONA_RAIO_CM)


# --- compute_angular_adjacency ---------------------------------------------------


def _item(buraco: int, angulo_deg: float, inicio_s: float, *, alvo: bool = False) -> VisitItem:
    return VisitItem(
        buraco_platform=buraco, angulo_deg_room=angulo_deg, inicio_s=inicio_s, dwell_s=1.0, alvo=alvo
    )


def test_direto_ao_alvo_sem_checagem_anterior():
    sequence = VisitSequence.avaliada([_item(0, TARGET_ANGLE, 1.0, alvo=True)])
    result = compute_angular_adjacency(
        sequence, target_angle_deg_room=TARGET_ANGLE, adjacencia_angular_graus=ADJ_GRAUS
    )
    assert result.buracos_platform == ()
    assert result.primeiro_buraco_distancia_deg is None
    assert result.maior_sequencia_buracos == 0
    assert not result.primary_censurado


def test_um_buraco_vizinho_antes_do_alvo():
    sequence = VisitSequence.avaliada(
        [_item(1, 45.0, 1.0), _item(0, TARGET_ANGLE, 2.0, alvo=True)]
    )
    result = compute_angular_adjacency(
        sequence, target_angle_deg_room=TARGET_ANGLE, adjacencia_angular_graus=ADJ_GRAUS
    )
    assert result.buracos_platform == (1,)
    assert result.primeiro_buraco_distancia_deg == pytest.approx(45.0)
    assert result.maior_sequencia_buracos == 1


def test_sequencia_serial_mesmo_sentido():
    """Três buracos a 45° um do outro, sempre no mesmo sentido: sequência de 3."""
    sequence = VisitSequence.avaliada(
        [
            _item(2, 90.0, 1.0),
            _item(3, 135.0, 2.0),
            _item(4, 180.0, 3.0),
            _item(0, TARGET_ANGLE, 4.0, alvo=True),
        ]
    )
    result = compute_angular_adjacency(
        sequence, target_angle_deg_room=TARGET_ANGLE, adjacencia_angular_graus=46.0
    )
    assert result.buracos_platform == (2, 3, 4)
    assert result.maior_sequencia_buracos == 3


def test_sentido_invertido_quebra_a_sequencia():
    """90 -> 135 (sentido +) -> 90 (sentido -): a reversão corta a sequência em 2."""
    sequence = VisitSequence.avaliada(
        [
            _item(2, 90.0, 1.0),
            _item(3, 135.0, 2.0),
            _item(2, 90.0, 3.0),
            _item(0, TARGET_ANGLE, 4.0, alvo=True),
        ]
    )
    result = compute_angular_adjacency(
        sequence, target_angle_deg_room=TARGET_ANGLE, adjacencia_angular_graus=46.0
    )
    assert result.maior_sequencia_buracos == 2


def test_buracos_distantes_nao_formam_sequencia():
    sequence = VisitSequence.avaliada(
        [
            _item(2, 90.0, 1.0),
            _item(5, 225.0, 2.0),
            _item(0, TARGET_ANGLE, 3.0, alvo=True),
        ]
    )
    result = compute_angular_adjacency(
        sequence, target_angle_deg_room=TARGET_ANGLE, adjacencia_angular_graus=ADJ_GRAUS
    )
    assert result.maior_sequencia_buracos == 1


def test_alvo_nao_checado_usa_sequencia_inteira_e_censura():
    sequence = VisitSequence.avaliada([_item(2, 90.0, 1.0), _item(3, 135.0, 2.0)])
    result = compute_angular_adjacency(
        sequence, target_angle_deg_room=TARGET_ANGLE, adjacencia_angular_graus=46.0
    )
    assert result.primary_censurado
    assert result.buracos_platform == (2, 3)
    assert result.maior_sequencia_buracos == 2
    assert any("não foi checado" in aviso for aviso in result.avisos)


def test_sequencia_nao_avaliada_recusada():
    with pytest.raises(SignalError, match="não calculada"):
        compute_angular_adjacency(
            VisitSequence.nao_avaliada(),
            target_angle_deg_room=TARGET_ANGLE,
            adjacencia_angular_graus=ADJ_GRAUS,
        )


def test_adjacencia_negativa_recusada():
    sequence = VisitSequence.avaliada([_item(0, TARGET_ANGLE, 1.0, alvo=True)])
    with pytest.raises(SignalError, match="adjacencia_angular_graus"):
        compute_angular_adjacency(
            sequence, target_angle_deg_room=TARGET_ANGLE, adjacencia_angular_graus=-1.0
        )


def test_angulo_alvo_fora_de_faixa_recusado():
    sequence = VisitSequence.avaliada([_item(0, TARGET_ANGLE, 1.0, alvo=True)])
    with pytest.raises(SignalError, match="target_angle_deg_room"):
        compute_angular_adjacency(
            sequence, target_angle_deg_room=360.0, adjacencia_angular_graus=ADJ_GRAUS
        )
