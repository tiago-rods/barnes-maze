"""Série temporal de posição e orientação da cabeça a partir da pose inferida (US-09).

Funções puras, sem banco nem GPU: recebem a pose bruta em pixels (o `pose.csv`
de `barnes.pose.inference.infer_trial`), a escala da montagem (US-02) e o
intervalo útil (US-03), e montam a tabela do contrato em
`barnes.pose.trajectory`. A orquestração (ler o banco, registrar a execução,
gravar o arquivo) fica na CLI.

Convenção angular (US-04, `docs/definicoes-metricas.md` §6.5): eixos da imagem,
y para baixo; θ = 0° aponta para +x e cresce no sentido horário na tela.
"""

from __future__ import annotations

import numpy as np


def px_to_cm(values_px: np.ndarray, cm_per_px: float) -> np.ndarray:
    """Converte coordenadas em pixel para cm com a escala da montagem (SCRUM-117).

    Usa um único fator para os dois eixos, como a calibração da US-02. NaN
    (ponto ausente) continua NaN.

    Args:
        values_px: Coordenadas em pixel, de qualquer formato.
        cm_per_px: Escala da montagem (`StoredCalibration.cm_per_px`).

    Returns:
        As mesmas coordenadas em cm, como float64.

    Raises:
        ValueError: Se a escala não for um número finito positivo.
    """
    if (
        isinstance(cm_per_px, bool)
        or not isinstance(cm_per_px, int | float)
        or not np.isfinite(cm_per_px)
        or cm_per_px <= 0
    ):
        raise ValueError("A escala cm_per_px deve ser um número finito e positivo.")
    return np.asarray(values_px, dtype=np.float64) * float(cm_per_px)


def head_angle_deg(
    center_x: np.ndarray, center_y: np.ndarray, snout_x: np.ndarray, snout_y: np.ndarray
) -> np.ndarray:
    """Orientação da cabeça pelo eixo centro do corpo → focinho, em graus (SCRUM-119).

    Nos eixos da imagem (y para baixo), `atan2(dy, dx)` dá 0° para +x e ângulos
    crescendo no sentido horário na tela — a convenção de `holes.angle_deg`.
    O resultado fica em [0, 360). É NaN quando falta algum dos dois pontos ou
    quando eles coincidem (direção indefinida); nunca herda o quadro anterior.

    Args:
        center_x, center_y: Centro do corpo (qualquer unidade; a mesma nos dois).
        snout_x, snout_y: Focinho.

    Returns:
        θ em graus, mesmo formato das entradas.
    """
    dx = np.asarray(snout_x, dtype=np.float64) - np.asarray(center_x, dtype=np.float64)
    dy = np.asarray(snout_y, dtype=np.float64) - np.asarray(center_y, dtype=np.float64)
    theta = np.degrees(np.arctan2(dy, dx)) % 360.0
    # % 360 de um negativo minúsculo pode dar exatamente 360.0.
    theta = np.where(theta >= 360.0, 0.0, theta)
    defined = np.isfinite(dx) & np.isfinite(dy) & ((dx != 0) | (dy != 0))
    return np.where(defined, theta, np.nan)
