"""Sequência cronológica de checagens US-15: ordenação, sala e contrato do US-17."""

from __future__ import annotations

import math

import pytest

from barnes.events.calibration import ManualAnnotations, ManualEvent
from barnes.events.entry import EntryEvent
from barnes.events.sequence import (
    SequenceError,
    blocked_sequence_round,
    build_sequence,
    compare_sequence,
    to_visit_sequence,
)
from barnes.geometry.holes import Hole, MazeGeometry
from barnes.metrics.errors import ErrorCriterion, ErrorDefinition, compute_errors


def _manual(holes, *, trial_id=7):
    return ManualAnnotations(
        trial_id=trial_id,
        observer="observador fixture",
        source="somente teste",
        delivered_on="2026-11-05",
        time_origin="intervalo_util",
        events=tuple(
            ManualEvent(tipo="entrada", hole_number=hole, t_s=float(index))
            for index, hole in enumerate(holes)
        ),
    )


def _geometry():
    return MazeGeometry(
        center_x_px=0.0,
        center_y_px=0.0,
        platform_radius_px=20.0,
        holes=(
            Hole(0, 0.0, 20.0, 0.0, 2.0, True),
            Hole(1, 90.0, 0.0, 20.0, 2.0, False),
            Hole(2, 180.0, -20.0, 0.0, 2.0, False),
        ),
    )


def _entry(
    hole,
    t_s,
    *,
    discovery_t_s=None,
    confirmed_at_s=None,
    dwell_s=0.3,
    dwell_interpolado=False,
    issues=(),
):
    return EntryEvent(
        hole_number=hole,
        quadro=int(t_s * 10),
        t_s=t_s,
        confirmed_at_s=t_s if confirmed_at_s is None else confirmed_at_s,
        delta_latency=None,
        delta_distance_cm=None,
        total_latency=None,
        total_distance_cm=None,
        discovery_quadro=None if discovery_t_s is None else int(discovery_t_s * 10),
        discovery_t_s=discovery_t_s,
        dwell_s=dwell_s,
        dwell_interpolado=dwell_interpolado,
        issues=issues,
    )


def test_reentry_does_not_collide_on_the_shared_discovery_time():
    # Mesma descoberta (t=0.0) para as duas entradas no buraco 0 (US-13
    # preserva reentradas, mas só emite D uma vez por buraco). Reproduz um
    # caso real encontrado ao conferir manualmente um trial de referência.
    entries = [_entry(0, 0.0, discovery_t_s=0.0), _entry(0, 0.5, discovery_t_s=0.0)]
    items = build_sequence(entries, geometry=_geometry(), rotation_deg=0.0)
    assert [item.inicio_s for item in items] == [0.0, 0.5]
    assert items[0].t_descoberta_s == items[1].t_descoberta_s == 0.0
    assert items[1].t_entrada_s == 0.5
    to_visit_sequence(items)  # não deve levantar por ordem não estritamente crescente


def test_discovery_after_first_entry_does_not_delay_the_visit():
    # Caso real (vídeo completo do LNBio, 12/11/2026): a primeira entrada no buraco
    # veio antes da descoberta (inconsistência D->E da US-13) e a reentrada caiu
    # exatamente no quadro da descoberta. Usar D como início da primeira visita
    # fazia as duas colidirem em inicio_s.
    entries = [
        _entry(0, 154.4, discovery_t_s=156.7, issues=("descoberta D posterior à entrada E",)),
        _entry(0, 156.7, discovery_t_s=156.7),
        _entry(0, 158.9, discovery_t_s=156.7),
    ]
    items = build_sequence(entries, geometry=_geometry(), rotation_deg=0.0)
    assert [item.inicio_s for item in items] == [154.4, 156.7, 158.9]
    assert items[0].t_descoberta_s == 156.7
    to_visit_sequence(items)


def test_sequence_is_ordered_by_start_and_numbered_from_one():
    entries = [_entry(2, 5.0, discovery_t_s=4.0), _entry(0, 1.0, discovery_t_s=0.5)]
    items = build_sequence(entries, geometry=_geometry(), rotation_deg=0.0)
    assert [item.ordem for item in items] == [1, 2]
    assert [item.buraco_platform for item in items] == [0, 2]
    assert [item.inicio_s for item in items] == [0.5, 4.0]


def test_room_frame_position_uses_reference_frame_conversion():
    items = build_sequence([_entry(1, 1.0, discovery_t_s=0.9)], geometry=_geometry(), rotation_deg=0.0)
    assert items[0].angulo_deg_room == pytest.approx(90.0)
    rotated = build_sequence(
        [_entry(1, 1.0, discovery_t_s=0.9)], geometry=_geometry(), rotation_deg=10.0
    )
    assert rotated[0].angulo_deg_room == pytest.approx(100.0)


def test_target_hole_is_marked_from_montagem_by_default():
    entries = [_entry(0, 1.0, discovery_t_s=0.5), _entry(1, 2.0, discovery_t_s=1.5)]
    items = build_sequence(entries, geometry=_geometry(), rotation_deg=0.0)
    assert [item.alvo for item in items] == [True, False]


def test_explicit_target_hole_number_overrides_montagem_flag():
    items = build_sequence(
        [_entry(1, 1.0, discovery_t_s=0.5)],
        geometry=_geometry(),
        rotation_deg=0.0,
        target_hole_number=1,
    )
    assert items[0].alvo is True


def test_orphan_entry_without_discovery_starts_at_its_own_entry_time():
    item = build_sequence([_entry(0, 3.0, discovery_t_s=None)], geometry=_geometry(), rotation_deg=0.0)[0]
    assert item.t_descoberta_s is None
    assert item.t_entrada_s == 3.0
    assert item.inicio_s == 3.0


def test_dwell_and_issues_are_carried_over_from_the_entry_event():
    item = build_sequence(
        [_entry(0, 1.0, discovery_t_s=0.5, dwell_s=0.7, dwell_interpolado=True, issues=("x",))],
        geometry=_geometry(),
        rotation_deg=0.0,
    )[0]
    assert item.dwell_s == 0.7
    assert item.dwell_interpolado is True
    assert item.issues == ("x",)


def test_empty_entries_produce_an_empty_sequence():
    assert build_sequence([], geometry=_geometry(), rotation_deg=0.0) == ()


def test_ambiguous_target_without_override_is_refused():
    geometry = _geometry()
    no_target = MazeGeometry(
        geometry.center_x_px,
        geometry.center_y_px,
        geometry.platform_radius_px,
        tuple(Hole(h.hole_number, h.angle_deg, h.x_px, h.y_px, h.radius_px, False) for h in geometry.holes),
    )
    with pytest.raises(SequenceError, match="único buraco-alvo"):
        build_sequence([_entry(0, 1.0)], geometry=no_target, rotation_deg=0.0)


def test_nonexistent_hole_in_entries_is_refused():
    with pytest.raises(SequenceError, match="inexistente"):
        build_sequence([_entry(7, 1.0)], geometry=_geometry(), rotation_deg=0.0)


def test_nonexistent_explicit_target_is_refused():
    with pytest.raises(SequenceError, match="inexistente"):
        build_sequence(
            [_entry(0, 1.0)], geometry=_geometry(), rotation_deg=0.0, target_hole_number=9
        )


def test_tied_start_times_are_refused_not_silently_ordered():
    entries = [_entry(0, 1.0, discovery_t_s=0.5), _entry(1, 2.0, discovery_t_s=0.5)]
    with pytest.raises(SequenceError, match="ordem cronológica estrita"):
        build_sequence(entries, geometry=_geometry(), rotation_deg=0.0)


def test_to_visit_sequence_feeds_us17_compute_errors_without_reopening_anything():
    entries = [
        _entry(1, 0.5, discovery_t_s=0.0, dwell_s=0.3),
        _entry(0, 2.0, discovery_t_s=1.5, dwell_s=0.4),
    ]
    items = build_sequence(entries, geometry=_geometry(), rotation_deg=0.0)
    result = compute_errors(
        to_visit_sequence(items), ErrorDefinition(ErrorCriterion.QUALQUER_BURACO_INCORRETO)
    )
    assert result.total == 1
    assert result.ate_alvo == 1
    assert result.buracos_platform == (1,)
    assert result.angulos_deg_room == (pytest.approx(90.0),)


def test_to_visit_sequence_preserves_missing_dwell_as_none_safe_value():
    # dwell_s do EntryEvent é sempre finito (US-14 nunca deixa NaN escapar);
    # aqui só confirmamos que o valor passa intacto para o VisitItem.
    items = build_sequence([_entry(0, 1.0, discovery_t_s=0.5, dwell_s=1.25)], geometry=_geometry(), rotation_deg=0.0)
    visit_sequence = to_visit_sequence(items)
    assert visit_sequence.itens[0].dwell_s == 1.25
    assert math.isfinite(visit_sequence.itens[0].dwell_s)


def test_compare_sequence_full_agreement_passes():
    report = compare_sequence(_manual([0, 1, 2]), [0, 1, 2])
    assert report["agreement"] == 1.0
    assert report["passed"] is True
    assert report["status"] == "passed"


def test_compare_sequence_partial_agreement_is_scored_not_rounded_up():
    # 1 de 4 posições coincide: 0,25 de concordância, abaixo do limiar 0,95.
    report = compare_sequence(_manual([0, 1, 2, 3]), [0, 5, 6, 7])
    assert report["agreement"] == pytest.approx(0.25)
    assert report["passed"] is False
    assert report["status"] == "divergence_review_required"


def test_compare_sequence_different_lengths_count_missing_positions_as_divergence():
    # 2 posições coincidem, mas a automática tem 1 checagem extra sem par manual.
    report = compare_sequence(_manual([0, 1]), [0, 1, 2])
    assert report["agreement"] == pytest.approx(2 / 3)
    assert report["manual_sequence"] == [0, 1]
    assert report["automatic_sequence"] == [0, 1, 2]


def test_compare_sequence_ignores_manual_discoveries_and_sorts_by_time():
    manual = ManualAnnotations(
        trial_id=7,
        observer="observador fixture",
        source="somente teste",
        delivered_on="2026-11-05",
        time_origin="intervalo_util",
        events=(
            ManualEvent(tipo="descoberta", hole_number=9, t_s=0.0),
            ManualEvent(tipo="entrada", hole_number=2, t_s=5.0),
            ManualEvent(tipo="entrada", hole_number=1, t_s=1.0),
        ),
    )
    report = compare_sequence(manual, [1, 2])
    assert report["manual_sequence"] == [1, 2]
    assert report["agreement"] == 1.0


def test_blocked_sequence_round_never_claims_a_result():
    report = blocked_sequence_round(7)
    assert report["status"] == "blocked_missing_d3"
    assert report["passed"] is False
    assert report["manual_sequence"] is None
    assert report["automatic_sequence"] is None
