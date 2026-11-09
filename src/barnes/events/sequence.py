"""Sequência cronológica das checagens de buraco de um trial (US-15).

Uma checagem é uma entrada confirmada (E, US-13): "buraco checado" é o
critério físico de C2, não a simples descoberta (D, US-11) — notar um
buraco de longe não é checá-lo. Cada `EntryEvent` já traz a descoberta
pareada (`discovery_t_s`, pode ser `None` numa entrada órfã) e o dwell
(`dwell_s`/`dwell_interpolado`, US-14); este módulo só ordena, converte a
posição para o referencial da sala (US-05) e numera.

Função pura: não lê o banco nem a trajetória (RN03 — este módulo é a
entrada canônica dos Épicos E/F, que por isso também nunca releem a
trajetória). `to_visit_sequence` projeta o item completo no contrato mínimo
que `barnes.metrics.errors` (US-17) já fixa.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise

from barnes.events.entry import EntryEvent
from barnes.geometry.holes import MazeGeometry
from barnes.geometry.reference_frame import hole_to_room_angle
from barnes.metrics.errors import VisitItem, VisitSequence


class SequenceError(ValueError):
    """A sequência não pode ser montada com os dados fornecidos."""


@dataclass(frozen=True)
class SequenceItem:
    """Uma checagem de buraco na sequência de visitação (RN02).

    Attributes:
        ordem: Posição na sequência, 1-based.
        buraco_platform: Índice do buraco na montagem, 0..N-1.
        angulo_deg_room: Posição do buraco na sala, em graus [0, 360)
            (`barnes.geometry.reference_frame.hole_to_room_angle`).
        t_descoberta_s: Tempo da descoberta pareada (US-11), ou `None` numa
            entrada órfã (sem D anterior ou simultânea, US-13).
        t_entrada_s: Tempo de início da entrada confirmada (US-13).
        dwell_s: Permanência da checagem, em segundos (US-14).
        dwell_interpolado: Dwell apoiado em quadro interpolado (US-10/US-14).
        alvo: O buraco é o buraco-alvo do trial.
        issues: Inconsistências herdadas do `EntryEvent` de origem.
    """

    ordem: int
    buraco_platform: int
    angulo_deg_room: float
    t_descoberta_s: float | None
    t_entrada_s: float
    dwell_s: float
    dwell_interpolado: bool
    alvo: bool
    issues: tuple[str, ...] = ()

    @property
    def inicio_s(self) -> float:
        """Início da checagem (RN02): a descoberta, ou a própria entrada se órfã."""
        return self.t_entrada_s if self.t_descoberta_s is None else self.t_descoberta_s


def build_sequence(
    entries: Iterable[EntryEvent],
    *,
    geometry: MazeGeometry,
    rotation_deg: float,
    target_hole_number: int | None = None,
) -> tuple[SequenceItem, ...]:
    """Monta a sequência cronológica de checagens de um trial (RN01/RN02).

    Ordena por `inicio_s` (descoberta pareada, ou a própria entrada quando
    órfã — ver `SequenceItem.inicio_s`) e numera a partir de 1. Não
    reordena silenciosamente uma ordem ambígua: duas checagens com o mesmo
    `inicio_s` são um erro de quem produziu os eventos, não um empate a
    resolver aqui.

    Args:
        entries: Entradas confirmadas do trial (`barnes.events.entry`),
            tipicamente lidas de volta de `evento_buraco` (US-13/US-14).
        geometry: Montagem do trial.
        rotation_deg: Rotação da plataforma no trial (US-05).
        target_hole_number: Buraco-alvo efetivo, já resolvido para a
            rotação (ver `barnes.geometry.reference_frame.target_hole_for_trial`).
            Sem valor, usa o único `is_target` da montagem.

    Raises:
        SequenceError: Lista de entradas vazia é aceita (trial sem nenhuma
            checagem é um resultado real); erro só em ambiguidade de alvo,
            buraco inexistente ou ordem não estritamente crescente.
    """
    holes = {hole.hole_number for hole in geometry.holes}
    if target_hole_number is None:
        targets = [hole.hole_number for hole in geometry.holes if hole.is_target]
        if len(targets) != 1:
            raise SequenceError("A montagem deve ter um único buraco-alvo.")
        target_hole_number = targets[0]
    elif target_hole_number not in holes:
        raise SequenceError(f"Buraco-alvo inexistente na montagem: {target_hole_number}.")

    staged = []
    for entry in entries:
        if entry.hole_number not in holes:
            raise SequenceError(f"Entrada refere buraco inexistente: {entry.hole_number}.")
        inicio_s = entry.t_s if entry.discovery_t_s is None else entry.discovery_t_s
        staged.append((inicio_s, entry))
    staged.sort(key=lambda pair: pair[0])

    items = []
    for ordem, (inicio_s, entry) in enumerate(staged, start=1):
        items.append(
            SequenceItem(
                ordem=ordem,
                buraco_platform=entry.hole_number,
                angulo_deg_room=hole_to_room_angle(
                    geometry, entry.hole_number, rotation_deg=rotation_deg
                ),
                t_descoberta_s=entry.discovery_t_s,
                t_entrada_s=entry.t_s,
                dwell_s=entry.dwell_s,
                dwell_interpolado=entry.dwell_interpolado,
                alvo=entry.hole_number == target_hole_number,
                issues=entry.issues,
            )
        )

    for anterior, atual in pairwise(items):
        if not math.isfinite(atual.inicio_s) or atual.inicio_s <= anterior.inicio_s:
            raise SequenceError(
                f"Sequência fora de ordem cronológica estrita: checagem do buraco "
                f"{atual.buraco_platform} em inicio_s={atual.inicio_s} não é posterior à "
                f"checagem do buraco {anterior.buraco_platform} em inicio_s={anterior.inicio_s}."
            )

    return tuple(items)


def to_visit_sequence(items: Iterable[SequenceItem]) -> VisitSequence:
    """Projeta a sequência completa no contrato mínimo do US-17 (RN03).

    `VisitItem`/`VisitSequence` (`barnes.metrics.errors`) já existem e já
    validam ordem estrita e alvo único; esta função não duplica essas
    checagens, só remapeia os campos.
    """
    return VisitSequence.avaliada(
        VisitItem(
            buraco_platform=item.buraco_platform,
            angulo_deg_room=item.angulo_deg_room,
            inicio_s=item.inicio_s,
            dwell_s=item.dwell_s,
            alvo=item.alvo,
        )
        for item in items
    )
