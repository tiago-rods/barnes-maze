"""Entrada física US-13: duração observada, reentradas, D->E e qualidade."""

from __future__ import annotations

import math
from dataclasses import replace

import pyarrow as pa
import pytest

from barnes.events.discovery import DiscoveryEvent
from barnes.events.entry import (
    EntryConfigError,
    EntryDetectionError,
    EntryParams,
    detect_entries,
    load_entry_params,
)
from barnes.geometry.holes import Hole, MazeGeometry

PARAMS = EntryParams(radius_factor=1.0, minimum_duration_s=0.2)


def _geometry():
    return MazeGeometry(
        center_x_px=0.0,
        center_y_px=0.0,
        platform_radius_px=20.0,
        holes=(Hole(0, 0.0, 20.0, 0.0, 2.0, True), Hole(1, 180.0, -20.0, 0.0, 2.0, False)),
    )


def _table(
    nose_x,
    *,
    times=None,
    frames=None,
    center_x=None,
    center_y=None,
    valid=None,
    center_valid=None,
    nose_y=None,
):
    size = len(nose_x)
    return pa.table(
        {
            "quadro": pa.array(frames if frames is not None else range(size), type=pa.int32()),
            "t_s": pa.array(
                times if times is not None else [index / 10 for index in range(size)],
                type=pa.float64(),
            ),
            "focinho_x_cm_image": pa.array(nose_x, type=pa.float64()),
            "focinho_y_cm_image": pa.array(
                nose_y if nose_y is not None else [0.0] * size, type=pa.float64()
            ),
            "centro_corpo_x_cm_image": pa.array(
                center_x if center_x is not None else range(size), type=pa.float64()
            ),
            "centro_corpo_y_cm_image": pa.array(
                center_y if center_y is not None else [0.0] * size, type=pa.float64()
            ),
            "pose_valida": pa.array(valid if valid is not None else [True] * size, type=pa.bool_()),
            "centro_corpo_valido": pa.array(
                center_valid if center_valid is not None else [True] * size, type=pa.bool_()
            ),
        }
    )


def _d(hole=0, frame=0, time=0.0):
    return DiscoveryEvent(
        hole_number=hole, quadro=frame, t_s=time, distancia_cm=1.0, angulo_deg=0.0
    )


def _detect(table, discoveries=None, **kwargs):
    return detect_entries(
        table,
        kwargs.pop("geometry", _geometry()),
        kwargs.pop("cm_per_px", 1.0),
        kwargs.pop("params", PARAMS),
        [_d()] if discoveries is None else discoveries,
        trial_id=41,
        **kwargs,
    )


def _config(tmp_path, section):
    import yaml

    path = tmp_path / "custom.yaml"
    path.write_text(yaml.safe_dump({"entrar": section}), encoding="utf-8")
    return path


def test_load_config_requires_explicit_c2_values(tmp_path):
    values = {"raio_fator": 1.25, "duracao_minima_s": 0.35, "focinho_dentro": True}
    assert load_entry_params(_config(tmp_path, values)) == EntryParams(1.25, 0.35)
    for key in values:
        with pytest.raises(EntryConfigError, match=f"entrar.{key}"):
            load_entry_params(_config(tmp_path, values | {key: None}))
        with pytest.raises(EntryConfigError, match=f"entrar.{key}"):
            load_entry_params(
                _config(tmp_path, {name: value for name, value in values.items() if name != key})
            )


@pytest.mark.parametrize(
    "key,value",
    [
        ("raio_fator", 0),
        ("raio_fator", -1),
        ("raio_fator", math.nan),
        ("raio_fator", math.inf),
        ("raio_fator", True),
        ("raio_fator", "1"),
        ("duracao_minima_s", 0),
        ("duracao_minima_s", -1),
        ("duracao_minima_s", math.nan),
        ("duracao_minima_s", math.inf),
        ("duracao_minima_s", True),
        ("duracao_minima_s", "1"),
        ("focinho_dentro", False),
        ("focinho_dentro", "true"),
        ("focinho_dentro", 1),
    ],
)
def test_config_refuses_unsupported_values(tmp_path, key, value):
    values = {"raio_fator": 1.0, "duracao_minima_s": 0.2, "focinho_dentro": True}
    with pytest.raises(EntryConfigError, match=f"entrar.{key}"):
        load_entry_params(_config(tmp_path, values | {key: value}))


@pytest.mark.parametrize("body", ["[]", "{}", "entrar: []", "entrar: ["])
def test_missing_or_malformed_yaml_is_refused(tmp_path, body):
    path = tmp_path / "invalid.yaml"
    path.write_text(body)
    with pytest.raises(EntryConfigError):
        load_entry_params(path)
    with pytest.raises(EntryConfigError):
        load_entry_params(tmp_path / "missing.yaml")


def test_entry_records_onset_and_confirmation_plus_path_distance():
    # Caminho do centro tem passos de 5,5,5 cm, não a distância em linha reta.
    table = _table(
        [0, 0, 20, 20, 20, 20], center_x=[0, 3, 6, 9, 12, 15], center_y=[0, 4, 0, 4, 0, 4]
    )
    events = _detect(table, [_d(frame=1, time=0.1)])
    assert len(events) == 1
    event = events[0]
    assert (event.quadro, event.t_s, event.confirmed_at_s) == (2, 0.2, 0.4)
    assert event.delta_latency == pytest.approx(0.1)
    assert event.delta_distance_cm == pytest.approx(5)
    assert event.total_latency == 0.2
    assert event.total_distance_cm == pytest.approx(10)
    assert (event.discovery_quadro, event.discovery_t_s) == (1, 0.1)
    assert event.issues == ()


def test_actual_timestamps_determine_dwell_instead_of_frame_count():
    table = _table([20] * 4, times=[0.0, 0.01, 0.02, 0.25])
    event = _detect(table)[0]
    assert event.t_s == 0
    assert event.confirmed_at_s == 0.25
    assert event.delta_latency == event.delta_distance_cm == 0
    assert event.total_distance_cm == 0
    assert _detect(_table([20] * 4, times=[0.0, 0.01, 0.02, 0.19])) == []


def test_threshold_equality_survives_floating_point_subtraction():
    table = _table([0, 20, 20, 20], times=[0.0, 0.1, 0.2, 0.3])
    event = _detect(table)[0]
    assert event.t_s == 0.1
    assert event.confirmed_at_s == 0.3


def test_single_sample_never_establishes_positive_dwell():
    assert _detect(_table([20]), params=EntryParams(1.0, 1e-15)) == []


def test_circle_boundary_is_inside_and_radius_uses_scale_and_factor():
    # Buraco a 20px -> 10cm; raio2px * 0.5cm/px * fator2 = 2cm.
    events = _detect(_table([12.0] * 3), cm_per_px=0.5, params=EntryParams(2.0, 0.2))
    assert len(events) == 1
    assert _detect(_table([12.0001] * 3), cm_per_px=0.5, params=EntryParams(2.0, 0.2)) == []


@pytest.mark.parametrize("kind", ["outside", "invalid_pose", "nan_nose", "inf_nose", "frame_gap"])
def test_interruption_restarts_dwell(kind):
    frames = [0, 1, 2, 3, 4, 5]
    nose = [20.0] * 6
    valid = [True] * 6
    if kind == "outside":
        nose[2] = 0.0
    elif kind == "invalid_pose":
        valid[2] = False
    elif kind == "nan_nose":
        nose[2] = math.nan
    elif kind == "inf_nose":
        nose[2] = math.inf
    else:
        frames = [0, 1, 4, 5, 6, 7]
    events = _detect(_table(nose, frames=frames, valid=valid))
    assert len(events) == 1
    expected_start = 2 if kind == "frame_gap" else 3
    assert events[0].quadro == frames[expected_start]
    assert events[0].confirmed_at_s == pytest.approx((expected_start + 2) / 10)


def test_every_distinct_qualified_segment_is_recorded_once():
    table = _table([20, 20, 20, 20, 0, 20, 20, 20, 20])
    events = _detect(table)
    assert [event.quadro for event in events] == [0, 5]
    assert [event.confirmed_at_s for event in events] == [0.2, 0.7]
    assert [event.discovery_quadro for event in events] == [0, 0]
    assert [event.delta_distance_cm for event in events] == [0, 5]


def test_dwell_covers_the_whole_segment_not_just_the_confirmation_window():
    # Entra em t=0, confirma em 0.2s (RN de entrada), mas só sai em 0.5s.
    event = _detect(_table([20] * 6))[0]
    assert event.confirmed_at_s == 0.2
    assert event.dwell_s == pytest.approx(0.5)
    assert event.dwell_s > event.confirmed_at_s - event.t_s


def test_dwell_matches_confirmation_window_when_segment_ends_right_after_it():
    event = _detect(_table([20, 20, 20, 0]))[0]
    assert event.confirmed_at_s == 0.2
    assert event.dwell_s == pytest.approx(0.2)


def test_dwell_extends_to_last_sample_when_segment_is_still_open_at_the_end():
    event = _detect(_table([20] * 4))[0]
    assert event.confirmed_at_s == 0.2
    assert event.dwell_s == pytest.approx(0.3)


def test_each_reentry_gets_its_own_independent_dwell():
    table = _table([20, 20, 20, 20, 0, 20, 20, 20, 20])
    events = _detect(table)
    assert [event.quadro for event in events] == [0, 5]
    assert [event.dwell_s for event in events] == [pytest.approx(0.3), pytest.approx(0.3)]


def test_dwell_is_marked_when_any_frame_of_the_segment_was_interpolated():
    table = _table([20] * 4).append_column(
        "interpolado", pa.array([False, False, True, False], type=pa.bool_())
    )
    event = _detect(table)[0]
    assert event.dwell_interpolado is True


def test_dwell_is_not_marked_when_no_frame_of_the_segment_was_interpolated():
    table = _table([20] * 4).append_column(
        "interpolado", pa.array([False] * 4, type=pa.bool_())
    )
    event = _detect(table)[0]
    assert event.dwell_interpolado is False


def test_dwell_without_interpolado_column_defaults_to_not_marked():
    event = _detect(_table([20] * 4))[0]
    assert event.dwell_interpolado is False


def test_sum_of_dwells_never_exceeds_the_measured_time_span():
    # Duas reentradas no buraco 1 e uma no 0, intercaladas por saídas; os
    # buracos da montagem não se sobrepõem (RN03 depende dessa premissa).
    table = _table([-20, -20, -20, 0, 20, 20, 20, 20, 0, -20, -20, -20])
    events = _detect(table, [_d(), _d(hole=1)])
    span = table.column("t_s")[-1].as_py() - table.column("t_s")[0].as_py()
    assert sum(event.dwell_s for event in events) <= span


def test_short_visit_does_not_replace_later_qualified_entry():
    events = _detect(_table([20, 20, 0, 20, 20, 20]))
    assert len(events) == 1
    assert events[0].quadro == 3


def test_entries_are_chronological_and_target_can_follow_trial_rotation():
    table = _table([-20, -20, -20, 0, 20, 20, 20])
    events = _detect(table, [_d(), _d(hole=1)], target_hole_number=1)
    assert [event.hole_number for event in events] == [1, 0]
    assert events[0].total_latency == events[0].total_distance_cm == 0
    assert events[1].total_latency is None
    assert events[1].total_distance_cm is None
    assert events[1].delta_latency == 0.4


def test_missing_discovery_preserves_orphan_entry_with_named_issue():
    event = _detect(_table([0, 20, 20, 20]), [])[0]
    assert event.t_s == 0.1
    assert event.delta_latency is event.delta_distance_cm is None
    assert event.discovery_quadro is event.discovery_t_s is None
    assert event.total_latency == 0.1
    assert event.total_distance_cm == 1
    assert "Trial 41, buraco 0" in event.issues[0]
    assert "sem descoberta" in event.issues[0]


def test_discovery_after_onset_is_late_even_when_before_confirmation():
    event = _detect(_table([0, 20, 20, 20]), [_d(frame=2, time=0.2)])[0]
    assert event.t_s == 0.1 and event.confirmed_at_s == 0.3
    assert event.delta_latency is event.delta_distance_cm is None
    assert event.discovery_t_s == 0.2
    assert any("posterior" in issue and "Trial 41, buraco 0" in issue for issue in event.issues)


@pytest.mark.parametrize("kind", ["nan_center", "false_flag", "missing_columns", "frame_gap"])
def test_distance_refuses_partial_center_path(kind):
    table = _table([0, 0, 0, 20, 20, 20])
    if kind == "nan_center":
        table = _table([0, 0, 0, 20, 20, 20], center_x=[0.0, math.nan, 2.0, 3.0, 4.0, 5.0])
    elif kind == "false_flag":
        table = _table([0, 0, 0, 20, 20, 20], center_valid=[True, False, True, True, True, True])
    elif kind == "missing_columns":
        table = table.drop(["centro_corpo_x_cm_image", "centro_corpo_y_cm_image"])
    else:
        table = _table([0, 0, 0, 20, 20, 20], frames=[0, 2, 3, 4, 5, 6])
    event = _detect(table)[0]
    assert event.delta_latency == pytest.approx(0.3)
    assert event.total_latency == 0.3
    assert event.delta_distance_cm is event.total_distance_cm is None
    assert len(event.issues) == 2
    assert all("Trial 41, buraco 0" in issue for issue in event.issues)


def test_gap_before_discovery_affects_total_but_not_delta_distance():
    table = _table([0, 0, 20, 20, 20], center_x=[math.nan, 1.0, 2.0, 3.0, 4.0])
    event = _detect(table, [_d(frame=1, time=0.1)])[0]
    assert event.delta_distance_cm == 1
    assert event.total_distance_cm is None
    assert len(event.issues) == 1 and "total_distance_cm" in event.issues[0]


def test_invalid_center_after_onset_does_not_change_completed_path():
    table = _table([0, 20, 20, 20], center_x=[0, 1, math.nan, 3])
    event = _detect(table)[0]
    assert event.delta_distance_cm == event.total_distance_cm == 1


def test_missing_discovery_frame_cannot_produce_a_partial_distance():
    table = _table([0, 20, 20, 20], frames=[5, 6, 7, 8], times=[0.5, 0.6, 0.7, 0.8])
    event = _detect(table, [_d(frame=4, time=0.4)])[0]
    assert event.delta_latency == pytest.approx(0.2)
    assert event.delta_distance_cm is None
    assert any("quadro D ausente" in issue for issue in event.issues)


def test_discovery_timestamp_must_correspond_to_its_frame():
    event = _detect(_table([0, 20, 20, 20]), [_d(frame=0, time=0.05)])[0]
    assert event.delta_latency is event.delta_distance_cm is None
    assert any("tempo D" in issue for issue in event.issues)


def test_unsorted_trajectory_is_normalized_without_mutation():
    original = _table([0, 20, 20, 20])
    shuffled = original.take([2, 0, 3, 1])
    assert _detect(shuffled) == _detect(original)
    assert shuffled.column("quadro").to_pylist() == [2, 0, 3, 1]


@pytest.mark.parametrize(
    "change",
    ["duplicate", "negative_frame", "backward_time", "nan_time", "negative_time", "other_trial"],
)
def test_ambiguous_trajectory_is_refused(change):
    table = _table([20, 20, 20])
    if change == "duplicate":
        table = _table([20, 20, 20], frames=[0, 0, 1])
    elif change == "negative_frame":
        table = _table([20, 20, 20], frames=[-1, 0, 1])
    elif change == "backward_time":
        table = _table([20, 20, 20], times=[0.0, 0.3, 0.2])
    elif change == "nan_time":
        table = _table([20, 20, 20], times=[0.0, math.nan, 0.2])
    elif change == "negative_time":
        table = _table([20, 20, 20], times=[-0.1, 0.0, 0.2])
    else:
        table = table.append_column("trial_id", pa.array([41, 42, 41]))
    with pytest.raises(EntryDetectionError, match="Trial 41"):
        _detect(table)


@pytest.mark.parametrize("value", [0, -1, math.nan, math.inf, True])
def test_invalid_scale_is_refused(value):
    with pytest.raises(EntryDetectionError, match="cm_per_px"):
        _detect(_table([20] * 3), cm_per_px=value)


def test_direct_parameters_geometry_and_discoveries_are_validated():
    table = _table([20] * 3)
    with pytest.raises(EntryConfigError):
        _detect(table, params=EntryParams(0, 0.2))
    with pytest.raises(EntryConfigError):
        _detect(table, params=EntryParams(1, 0.2, False))
    for target in (2, True, 0.0):
        with pytest.raises(EntryDetectionError, match="alvo"):
            _detect(table, target_hole_number=target)
    geometry = _geometry()
    invalid_hole = replace(geometry.holes[0], radius_px=math.inf)
    with pytest.raises(EntryDetectionError, match="radius"):
        _detect(table, geometry=replace(geometry, holes=(invalid_hole, geometry.holes[1])))
    with pytest.raises(EntryDetectionError, match="mais de uma"):
        _detect(table, [_d(), _d()])
    with pytest.raises(EntryDetectionError, match="inexistente"):
        _detect(table, [_d(hole=3)])
    with pytest.raises(EntryDetectionError, match="inválido"):
        _detect(table, [_d(time=math.nan)])


def test_empty_table_has_no_entries():
    assert _detect(_table([])) == []


def test_observed_nose_can_confirm_entry_without_body_orientation():
    # No contrato real, perder o centro invalida pose/theta, mas o focinho
    # observado continua localizável. E sobrevive com distância ausente.
    table = _table([0, 20, 20, 20], center_x=[0, math.nan, 2, 3], valid=[True, False, True, True])
    table = table.append_column("focinho_valido", pa.array([True] * 4))
    event = _detect(table)[0]
    assert event.t_s == 0.1 and event.confirmed_at_s == 0.3
    assert event.delta_latency == 0.1
    assert event.delta_distance_cm is None and event.total_distance_cm is None
    assert event.issues


def test_explicit_invalid_nose_breaks_continuity_even_with_finite_coordinates():
    table = _table([20] * 5).append_column(
        "focinho_valido", pa.array([True, False, True, True, True])
    )
    event = _detect(table)[0]
    assert event.t_s == 0.2 and event.confirmed_at_s == 0.4


def test_excessively_large_config_number_reports_domain_error(tmp_path):
    values = {"raio_fator": 10**400, "duracao_minima_s": 0.2, "focinho_dentro": True}
    with pytest.raises(EntryConfigError, match="intervalo numérico"):
        load_entry_params(_config(tmp_path, values))
