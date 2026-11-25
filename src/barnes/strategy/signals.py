"""Dois dos três sinais da classificação de estratégia (US-20 RN02).

O terceiro sinal — erros até o alvo — já existe (`barnes.metrics.errors.compute_errors`,
US-17) e não é duplicado aqui; `barnes.strategy.classification` o lê direto.

Função pura, sem banco e sem vídeo:

- `count_center_crossings`: cruzamentos do centro da plataforma, a partir da
  trajetória contínua (US-09) — rotação-invariante (o centro não se move com
  a rotação da plataforma, US-05), por isso não depende do referencial da sala.
- `compute_angular_adjacency`: adjacência angular dos buracos checados em
  sequência, a partir da **sequência de visitação da US-15** (contrato mínimo
  de `barnes.metrics.errors.VisitItem`, no referencial da sala — RN05), nunca
  da trajetória.

Ambos operam só até a primeira checagem do alvo (RN02, mesma janela do
`primary_errors` da US-17 e do `until_s` de `barnes.strategy.entropy`); sem o
alvo checado, usam a sequência/trajetória inteira e marcam censura, como a
US-17 (RN03 de lá).
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise
from math import isfinite

import numpy as np
import pyarrow as pa

from barnes.geometry.holes import MazeGeometry
from barnes.geometry.reference_frame import circular_distance_deg
from barnes.metrics.errors import VisitItem, VisitSequence
from barnes.metrics.latency import DEFAULT_DISTANCE_POINT, TRAJECTORY_POINTS


class SignalError(ValueError):
    """Entradas incoerentes para um sinal da classificação de estratégia (US-20)."""


# --- Sinal: cruzamentos do centro ----------------------------------------------


@dataclass(frozen=True)
class CenterCrossings:
    """Cruzamentos do centro da plataforma até o alvo (US-20 RN02).

    Um cruzamento é contado a cada **entrada** na zona central (transição de
    fora para dentro); permanecer dentro não soma de novo, e já começar
    dentro da zona não conta como cruzamento (não há "fora" anterior para
    confirmar a entrada) — fica em aviso.

    Attributes:
        cruzamentos: Número de entradas na zona central; `None` se não
            calculado (sem amostra válida no trecho).
        zona_raio_cm: Raio da zona central usado, em cm (auditoria).
        n_amostras: Amostras válidas usadas.
        ponto: Ponto do corpo usado.
        until_s: Tempo final do trecho considerado.
        avisos: Ressalvas legíveis.
    """

    cruzamentos: int | None
    zona_raio_cm: float
    n_amostras: int
    ponto: str
    until_s: float | None
    avisos: tuple[str, ...]

    @property
    def calculado(self) -> bool:
        return self.cruzamentos is not None


def count_center_crossings(
    trajectory: pa.Table,
    geometry: MazeGeometry,
    cm_per_px: float,
    *,
    zona_raio_frac: float,
    ponto: str = DEFAULT_DISTANCE_POINT,
    until_s: float | None = None,
) -> CenterCrossings:
    """Conta entradas na zona central da plataforma, até `until_s` (US-20 RN02).

    Args:
        trajectory: Trajetória do trial (`read_trajectory`).
        geometry: Montagem do trial (centro e raio da circunferência dos buracos).
        cm_per_px: Escala px->cm da montagem.
        zona_raio_frac: Fração de `platform_radius_px` que define a zona
            central (`estrategia.centro_zona_raio_frac`), em (0, 1).
        ponto: Ponto do corpo usado.
        until_s: Tempo final do trecho, em segundos desde S; `None` = trial
            inteiro (censura, RN03 da US-17).

    Raises:
        SignalError: Ponto desconhecido, colunas ausentes, `zona_raio_frac`
            fora de (0, 1) ou `until_s` inválido.
    """
    if ponto not in TRAJECTORY_POINTS:
        raise SignalError(f"Ponto '{ponto}' desconhecido; use um de {', '.join(TRAJECTORY_POINTS)}.")
    if (
        isinstance(zona_raio_frac, bool)
        or not isinstance(zona_raio_frac, int | float)
        or not 0 < zona_raio_frac < 1
    ):
        raise SignalError("'zona_raio_frac' deve estar entre 0 e 1 (exclusivo).")
    if until_s is not None and (
        isinstance(until_s, bool) or not isinstance(until_s, int | float) or not isfinite(until_s)
    ):
        raise SignalError("'until_s' deve ser um número finito de segundos, ou None.")
    if until_s is not None and until_s < 0:
        raise SignalError(f"'until_s'={until_s} s é anterior a S (US-20).")

    columns = ("t_s", f"{ponto}_x_cm_image", f"{ponto}_y_cm_image", f"{ponto}_valido")
    missing = [name for name in columns if name not in trajectory.column_names]
    if missing:
        raise SignalError(f"Trajetória sem as colunas: {', '.join(missing)}.")
    t_s, x_cm, y_cm, valid = (trajectory.column(name).to_numpy() for name in columns)
    valid = valid.astype(bool)

    keep = valid & (t_s >= 0)
    if until_s is not None:
        keep &= t_s <= until_s

    zona_raio_cm = geometry.platform_radius_px * cm_per_px * zona_raio_frac
    avisos: list[str] = []
    n_amostras = int(keep.sum())
    if n_amostras == 0:
        avisos.append("Cruzamentos não calculados: nenhuma amostra válida no trecho.")
        return CenterCrossings(
            cruzamentos=None,
            zona_raio_cm=zona_raio_cm,
            n_amostras=0,
            ponto=ponto,
            until_s=until_s,
            avisos=tuple(avisos),
        )

    center_x_cm = geometry.center_x_px * cm_per_px
    center_y_cm = geometry.center_y_px * cm_per_px
    distancia = np.hypot(x_cm[keep] - center_x_cm, y_cm[keep] - center_y_cm)
    dentro = distancia <= zona_raio_cm

    if dentro[0]:
        avisos.append(
            "A primeira amostra do trecho já está dentro da zona central: não contada como "
            "cruzamento (sem transição de fora para dentro observada)."
        )
    entradas = np.flatnonzero(dentro[1:] & ~dentro[:-1])
    cruzamentos = int(entradas.size)

    return CenterCrossings(
        cruzamentos=cruzamentos,
        zona_raio_cm=zona_raio_cm,
        n_amostras=n_amostras,
        ponto=ponto,
        until_s=until_s,
        avisos=tuple(avisos),
    )


# --- Sinal: adjacência angular dos buracos checados ----------------------------


@dataclass(frozen=True)
class AngularAdjacency:
    """Adjacência angular dos buracos checados em sequência, até o alvo (RN02, RN05).

    Attributes:
        buracos_platform: Buracos checados antes do alvo, em ordem cronológica
            (índices da montagem; nunca inclui o próprio alvo).
        primeiro_buraco_distancia_deg: Distância angular circular (sala, RN05)
            do primeiro buraco checado até o alvo; `None` se nenhum buraco foi
            checado antes do alvo (foi direto).
        maior_sequencia_buracos: Comprimento (em buracos) da maior sequência de
            checagens consecutivamente adjacentes entre si, no mesmo sentido
            (horário ou anti-horário); 0 ou 1 se não há nenhum par adjacente.
        primary_censurado: O alvo não foi checado na sequência — os buracos
            cobrem o trial inteiro, não só o trecho "até o alvo" (mesma
            convenção de `TrialErrors.primary_censurado`, US-17).
        avisos: Ressalvas legíveis.
    """

    buracos_platform: tuple[int, ...]
    primeiro_buraco_distancia_deg: float | None
    maior_sequencia_buracos: int
    primary_censurado: bool
    avisos: tuple[str, ...]


def _pre_target_items(sequence: VisitSequence) -> tuple[tuple[VisitItem, ...], bool]:
    """Buracos checados antes do alvo, espelhando o corte de `compute_errors` (US-17).

    Primeira checagem do alvo é o corte (RN03 da US-17): buracos com
    `inicio_s` anterior a ela contam; sem alvo checado, a sequência inteira
    conta e fica marcada como censurada.
    """
    itens = sequence.itens
    primeiro_alvo = next((item.inicio_s for item in itens if item.alvo), None)
    if primeiro_alvo is None:
        return tuple(item for item in itens if not item.alvo), True
    return tuple(item for item in itens if not item.alvo and item.inicio_s < primeiro_alvo), False


def _run_signed_delta_deg(a_deg: float, b_deg: float) -> float:
    """Diferença angular com sinal, em (-180, 180], de `a_deg` para `b_deg`."""
    return ((b_deg - a_deg + 180.0) % 360.0) - 180.0


def _longest_adjacent_run(angles_deg: Iterable[float], limiar_deg: float) -> int:
    angles = list(angles_deg)
    if len(angles) < 2:
        return len(angles)
    best = 1
    run = 1
    run_sign = 0.0
    for a, b in pairwise(angles):
        delta = _run_signed_delta_deg(a, b)
        sign = math.copysign(1.0, delta) if delta != 0 else 0.0
        adjacent = 0 < abs(delta) <= limiar_deg
        if adjacent and (run_sign == 0.0 or sign == run_sign):
            run += 1
            run_sign = sign
        elif adjacent:
            run = 2
            run_sign = sign
        else:
            run = 1
            run_sign = 0.0
        best = max(best, run)
    return best


def compute_angular_adjacency(
    sequence: VisitSequence, *, target_angle_deg_room: float, adjacencia_angular_graus: float
) -> AngularAdjacency:
    """Adjacência angular dos buracos checados antes do alvo (RN02, RN05).

    Args:
        sequence: Sequência de visitação da US-15, no referencial da sala
            (`VisitSequence.avaliada`). `nao_avaliada()` é recusada: sem
            sequência, nada é calculado (como em US-17).
        target_angle_deg_room: Ângulo do buraco-alvo na sala, no referencial
            da sala (`barnes.geometry.reference_frame.target_room_angle`),
            explícito para não depender de o alvo ter sido checado.
        adjacencia_angular_graus: Limiar de distância angular circular para
            "um buraco de distância" (`estrategia.adjacencia_angular_graus`).

    Raises:
        SignalError: Sequência não avaliada, ou `adjacencia_angular_graus`/
            `target_angle_deg_room` inválidos.
    """
    if not sequence.disponivel:
        raise SignalError(
            "Adjacência angular não calculada: a sequência de visitação (US-15) não está "
            "disponível (US-20 RN05 exige a sequência, não a trajetória)."
        )
    if (
        isinstance(adjacencia_angular_graus, bool)
        or not isinstance(adjacencia_angular_graus, int | float)
        or not isfinite(adjacencia_angular_graus)
        or adjacencia_angular_graus < 0
    ):
        raise SignalError("'adjacencia_angular_graus' deve ser um número finito >= 0.")
    if (
        isinstance(target_angle_deg_room, bool)
        or not isinstance(target_angle_deg_room, int | float)
        or not isfinite(target_angle_deg_room)
        or not 0 <= target_angle_deg_room < 360
    ):
        raise SignalError("'target_angle_deg_room' deve ser um ângulo finito em [0, 360).")

    pre_alvo, censurado = _pre_target_items(sequence)
    buracos = tuple(item.buraco_platform for item in pre_alvo)
    angulos = tuple(item.angulo_deg_room for item in pre_alvo)

    primeiro_distancia = (
        None if not angulos else float(circular_distance_deg(angulos[0], target_angle_deg_room))
    )
    maior_sequencia = _longest_adjacent_run(angulos, adjacencia_angular_graus)

    avisos: list[str] = []
    if censurado:
        avisos.append(
            "O alvo não foi checado na sequência: a adjacência considera o trial inteiro, "
            "marcado como censurado (mesma convenção da US-17)."
        )

    return AngularAdjacency(
        buracos_platform=buracos,
        primeiro_buraco_distancia_deg=primeiro_distancia,
        maior_sequencia_buracos=maior_sequencia,
        primary_censurado=censurado,
        avisos=tuple(avisos),
    )
