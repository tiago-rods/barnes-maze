"""Índice de entropia da trajetória (US-20): cálculo puro, sem banco nem vídeo."""

from __future__ import annotations

import math

import numpy as np
import pyarrow as pa
import pytest

from barnes.geometry.holes import generate_holes
from barnes.strategy.entropy import EntropyError, compute_trajectory_entropy

CM_PER_PX = 0.5
FPS = 25.0
STEP_S = 1.0 / FPS

# Montagem sintética: plataforma centrada em (200, 200) px, 8 buracos (8 setores).
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


def _table(points, *, valid=None, fps_variavel=False) -> pa.Table:
    xy = np.asarray(points, dtype=float)
    n = len(xy)
    valid = np.ones(n, dtype=bool) if valid is None else np.asarray(valid, dtype=bool)
    x = np.where(valid, xy[:, 0], np.nan)
    y = np.where(valid, xy[:, 1], np.nan)
    return pa.table(
        {
            "t_s": np.arange(n) * STEP_S,
            "centro_corpo_x_cm_image": x,
            "centro_corpo_y_cm_image": y,
            "centro_corpo_valido": valid,
            "fps_variavel": np.full(n, fps_variavel, dtype=bool),
        }
    )


def _point_at(angle_deg: float, radius: float = RADIUS_CM) -> tuple[float, float]:
    a = math.radians(angle_deg)
    return (CENTER_CM[0] + radius * math.cos(a), CENTER_CM[1] + radius * math.sin(a))


def test_trajetoria_concentrada_entropia_zero():
    """Parado num único setor: entropia 0 bits (nenhuma dispersão)."""
    pontos = [_point_at(10.0)] * 50
    result = compute_trajectory_entropy(_table(pontos), GEOMETRY, CM_PER_PX, n_setores=8)
    assert result.calculado
    assert result.bits == pytest.approx(0.0, abs=1e-9)
    assert sum(result.contagem_por_setor) == 50
    assert result.n_setores == 8


def test_trajetoria_uniforme_entropia_maxima():
    """Mesmo número de amostras em cada um dos 8 setores: entropia = log2(8) = 3 bits."""
    angulos_centrais = np.arange(8) * 45.0 + 22.5  # meio de cada setor
    pontos = [_point_at(a) for a in angulos_centrais for _ in range(10)]
    result = compute_trajectory_entropy(_table(pontos), GEOMETRY, CM_PER_PX, n_setores=8)
    assert result.bits == pytest.approx(3.0, abs=1e-9)
    assert result.bits_maximo == pytest.approx(3.0)
    assert result.contagem_por_setor == (10,) * 8


def test_setor_padrao_e_numero_de_buracos_da_montagem():
    """Sem `n_setores` explícito, usa `geometry.hole_count` (8 na montagem sintética)."""
    pontos = [_point_at(10.0)] * 5
    result = compute_trajectory_entropy(_table(pontos), GEOMETRY, CM_PER_PX)
    assert result.n_setores == GEOMETRY.hole_count == 8


def test_sem_amostra_valida_entropia_none():
    pontos = [_point_at(10.0)] * 5
    result = compute_trajectory_entropy(
        _table(pontos, valid=[False] * 5), GEOMETRY, CM_PER_PX, n_setores=8
    )
    assert not result.calculado
    assert result.bits is None
    assert result.n_amostras == 0
    assert any("nenhuma amostra" in aviso for aviso in result.avisos)


def test_until_s_corta_amostras_posteriores():
    """Só as 3 primeiras amostras (num setor) importam; o resto (noutro setor) é ignorado."""
    pontos = [_point_at(10.0)] * 3 + [_point_at(190.0)] * 3
    table = _table(pontos)
    until_s = float(table.column("t_s")[2].as_py())
    result = compute_trajectory_entropy(table, GEOMETRY, CM_PER_PX, n_setores=8, until_s=until_s)
    assert result.n_amostras == 3
    assert result.bits == pytest.approx(0.0, abs=1e-9)


def test_fps_variavel_gera_aviso():
    pontos = [_point_at(10.0)] * 5
    result = compute_trajectory_entropy(
        _table(pontos, fps_variavel=True), GEOMETRY, CM_PER_PX, n_setores=8
    )
    assert any("fps variável" in aviso.lower() for aviso in result.avisos)


def test_ponto_desconhecido_recusado():
    pontos = [_point_at(10.0)] * 3
    with pytest.raises(EntropyError, match="desconhecido"):
        compute_trajectory_entropy(_table(pontos), GEOMETRY, CM_PER_PX, ponto="rabo")


def test_colunas_ausentes_recusadas():
    table = pa.table({"t_s": np.array([0.0, 0.04])})
    with pytest.raises(EntropyError, match="colunas"):
        compute_trajectory_entropy(table, GEOMETRY, CM_PER_PX)


def test_until_s_negativo_recusado():
    pontos = [_point_at(10.0)] * 3
    with pytest.raises(EntropyError, match="until_s"):
        compute_trajectory_entropy(_table(pontos), GEOMETRY, CM_PER_PX, until_s=-1.0)


def test_n_setores_invalido_recusado():
    pontos = [_point_at(10.0)] * 3
    with pytest.raises(EntropyError, match="n_setores"):
        compute_trajectory_entropy(_table(pontos), GEOMETRY, CM_PER_PX, n_setores=1)
