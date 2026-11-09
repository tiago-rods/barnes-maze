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
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise

from barnes.events.calibration import ManualAnnotations
from barnes.events.entry import EntryEvent
from barnes.geometry.holes import MazeGeometry, resolve_single_target
from barnes.geometry.reference_frame import hole_to_room_angle
from barnes.metrics.errors import VisitItem, VisitSequence

SEQUENCE_AGREEMENT_THRESHOLD = 0.95


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
        inicio_s: Início da checagem — chave de ordenação. É a descoberta
            pareada só na **primeira** visita cronológica a esse buraco;
            reentradas (RN de US-13, preservadas) começam no próprio
            `t_entrada_s`, porque a descoberta já foi "gasta" pela primeira
            visita e não pode originar duas checagens no mesmo instante.
        t_descoberta_s: Tempo da descoberta pareada (US-11), para exibição —
            `None` numa entrada órfã (sem D anterior ou simultânea, US-13).
            Preenchido mesmo numa reentrada (é a descoberta do buraco, não
            desta visita específica); use `inicio_s`, não este campo, para
            ordenar ou comparar tempos entre checagens.
        t_entrada_s: Tempo de início da entrada confirmada (US-13).
        dwell_s: Permanência da checagem, em segundos (US-14).
        dwell_interpolado: Dwell apoiado em quadro interpolado (US-10/US-14).
        alvo: O buraco é o buraco-alvo do trial.
        issues: Inconsistências herdadas do `EntryEvent` de origem.
    """

    ordem: int
    buraco_platform: int
    angulo_deg_room: float
    inicio_s: float
    t_descoberta_s: float | None
    t_entrada_s: float
    dwell_s: float
    dwell_interpolado: bool
    alvo: bool
    issues: tuple[str, ...] = ()


def build_sequence(
    entries: Iterable[EntryEvent],
    *,
    geometry: MazeGeometry,
    rotation_deg: float,
    target_hole_number: int | None = None,
) -> tuple[SequenceItem, ...]:
    """Monta a sequência cronológica de checagens de um trial (RN01/RN02).

    Ordena por `inicio_s` (ver `SequenceItem.inicio_s`: descoberta pareada só
    na primeira visita a cada buraco, própria entrada nas reentradas e nas
    órfãs) e numera a partir de 1. Não reordena silenciosamente uma ordem
    ambígua: duas checagens com o mesmo `inicio_s` são um erro de quem
    produziu os eventos, não um empate a resolver aqui.

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
        target_hole_number = resolve_single_target(geometry)
        if target_hole_number is None:
            raise SequenceError("A montagem deve ter um único buraco-alvo.")
    elif target_hole_number not in holes:
        raise SequenceError(f"Buraco-alvo inexistente na montagem: {target_hole_number}.")

    entries = list(entries)
    for entry in entries:
        if entry.hole_number not in holes:
            raise SequenceError(f"Entrada refere buraco inexistente: {entry.hole_number}.")

    # A descoberta é por buraco, não por visita: só a entrada cronologicamente
    # mais antiga de cada buraco pode usar o tempo de D como início — do
    # contrário, uma reentrada (US-13) colidiria no mesmo inicio_s da primeira.
    first_entry_by_hole: dict[int, EntryEvent] = {}
    for entry in entries:
        earliest = first_entry_by_hole.get(entry.hole_number)
        if earliest is None or entry.t_s < earliest.t_s:
            first_entry_by_hole[entry.hole_number] = entry

    staged = []
    for entry in entries:
        is_first_visit = first_entry_by_hole[entry.hole_number] is entry
        if is_first_visit and entry.discovery_t_s is not None:
            inicio_s = entry.discovery_t_s
        else:
            inicio_s = entry.t_s
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
                inicio_s=inicio_s,
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


def compare_sequence(manual: ManualAnnotations, automatic: Sequence[int]) -> dict:
    """Concordância entre a sequência de buracos checados e a anotação manual (RN04).

    A referência manual é a sequência de `hole_number` dos eventos
    ``tipo="entrada"`` do mesmo D3 já usado por US-12/13 (`ManualAnnotations`
    — nenhum formato novo). Concordância = fração de posições em que as duas
    sequências coincidem, sobre o tamanho da maior; sequências de tamanhos
    diferentes nunca são truncadas em silêncio — a posição que falta de um
    lado conta como divergência.
    """
    if not isinstance(manual, ManualAnnotations):
        raise SequenceError("É necessária uma referência ManualAnnotations válida de D3.")
    manual_sequence = tuple(
        event.hole_number
        for event in sorted((e for e in manual.events if e.tipo == "entrada"), key=lambda e: e.t_s)
    )
    automatic_sequence = tuple(automatic)
    length = max(len(manual_sequence), len(automatic_sequence))
    agreement = (
        1.0
        if length == 0
        else sum(
            manual_hole == auto_hole
            for manual_hole, auto_hole in zip(manual_sequence, automatic_sequence, strict=False)
        )
        / length
    )
    passed = agreement >= SEQUENCE_AGREEMENT_THRESHOLD
    return {
        "schema_version": 1,
        "story": "US-15",
        "kind": "sequencia",
        "trial_id": manual.trial_id,
        "manual_sequence": list(manual_sequence),
        "automatic_sequence": list(automatic_sequence),
        "agreement": agreement,
        "threshold": SEQUENCE_AGREEMENT_THRESHOLD,
        "passed": passed,
        "status": "passed" if passed else "divergence_review_required",
    }


def blocked_sequence_round(trial_id: int | None) -> dict:
    """Registra a dependência externa (D3 ausente), sem inventar referência (RN04)."""
    return {
        "schema_version": 1,
        "story": "US-15",
        "kind": "sequencia",
        "trial_id": trial_id,
        "status": "blocked_missing_d3",
        "passed": False,
        "manual_sequence": None,
        "automatic_sequence": None,
        "agreement": None,
        "threshold": SEQUENCE_AGREEMENT_THRESHOLD,
        "reason": "Anotação manual D3 do laboratório não entregue ou não confirmada.",
    }
