"""Comando `barnes events sequence` (US-15): lê evento_buraco, nunca a trajetória."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from barnes import cli, cli_events
from barnes.db.hole_events import HoleEvent
from barnes.db.trials import StoredTrial
from barnes.events.entry import EntryEvent
from barnes.geometry.holes import Hole, MazeGeometry

runner = CliRunner()


def _entry_event(hole, t_s, *, discovery_t_s=None, dwell_s=0.3, execucao_id=501):
    event = EntryEvent(
        hole_number=hole,
        quadro=int(t_s * 10),
        t_s=t_s,
        confirmed_at_s=t_s,
        delta_latency=None,
        delta_distance_cm=None,
        total_latency=None,
        total_distance_cm=None,
        discovery_quadro=None if discovery_t_s is None else int(discovery_t_s * 10),
        discovery_t_s=discovery_t_s,
        dwell_s=dwell_s,
        dwell_interpolado=False,
        issues=(),
    )
    return HoleEvent(
        id=hole,
        trial_id=7,
        hole_id=10 + hole,
        execucao_id=execucao_id,
        tipo="entrada",
        quadro=event.quadro,
        t_s=event.t_s,
        distancia_cm=None,
        angulo_deg=None,
        details=asdict(event),
    )


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    geometry = MazeGeometry(
        0.0, 0.0, 20.0, (Hole(0, 0.0, 20.0, 0.0, 2.0, True), Hole(1, 180.0, -20.0, 0.0, 2.0, False))
    )
    stored = StoredTrial(id=7, maze_config_id=3, width_px=100, height_px=100, interval=None)
    state = SimpleNamespace(events=[], rotation=0, out=tmp_path / "out")

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(cli_events, "get_connection", lambda dsn: Connection())
    monkeypatch.setattr(cli_events, "get_trial", lambda conn, trial: stored)
    monkeypatch.setattr(cli_events, "get_maze_config", lambda conn, maze: geometry)
    monkeypatch.setattr(cli_events, "get_trial_rotations", lambda conn, trials: {7: state.rotation})
    monkeypatch.setattr(cli_events, "list_hole_events", lambda conn, *, trial_id: state.events)
    return state


def invoke(scenario, *extra):
    return runner.invoke(
        cli.app,
        ["events", "sequence", "--trial", "7", "--out", str(scenario.out), *map(str, extra)],
    )


def _d3(tmp_path, holes, *, trial_id=7):
    document = {
        "trial_id": trial_id,
        "observer": "fixture sintética",
        "source": "somente teste",
        "delivered_on": "2026-11-05",
        "time_origin": "intervalo_util",
        "events": [{"tipo": "entrada", "hole_number": hole, "t_s": index} for index, hole in enumerate(holes)],
    }
    path = tmp_path / "d3.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_sequence_is_exported_ordered_without_touching_the_trajectory(scenario):
    scenario.events = [
        _entry_event(1, 0.5, discovery_t_s=0.0),
        _entry_event(0, 2.0, discovery_t_s=1.5),
    ]
    result = invoke(scenario)
    assert result.exit_code == 0, result.output
    report = json.loads(next(scenario.out.glob("*/sequence.json")).read_text(encoding="utf-8"))
    assert report["source_execucao_id"] == 501
    assert [item["buraco_platform"] for item in report["itens"]] == [1, 0]
    assert [item["alvo"] for item in report["itens"]] == [False, True]
    with next(scenario.out.glob("*/sequencia.csv")).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["ordem"] for row in rows] == ["1", "2"]
    assert rows[0]["angulo_deg_room"] == "180.0"


def test_only_the_latest_entry_execution_is_used(scenario):
    scenario.events = [
        _entry_event(0, 1.0, discovery_t_s=0.5, execucao_id=501),
        _entry_event(1, 2.0, discovery_t_s=1.5, execucao_id=600),
    ]
    result = invoke(scenario)
    assert result.exit_code == 0, result.output
    report = json.loads(next(scenario.out.glob("*/sequence.json")).read_text(encoding="utf-8"))
    assert report["source_execucao_id"] == 600
    assert [item["buraco_platform"] for item in report["itens"]] == [1]


def test_trial_without_any_entry_produces_an_empty_sequence(scenario):
    scenario.events = []
    result = invoke(scenario)
    assert result.exit_code == 0, result.output
    report = json.loads(next(scenario.out.glob("*/sequence.json")).read_text(encoding="utf-8"))
    assert report["itens"] == []
    assert report["source_execucao_id"] is None


def test_discovery_only_rows_are_not_treated_as_checks(scenario):
    discovery = _entry_event(0, 1.0)
    discovery = HoleEvent(
        id=discovery.id,
        trial_id=discovery.trial_id,
        hole_id=discovery.hole_id,
        execucao_id=discovery.execucao_id,
        tipo="descoberta",
        quadro=discovery.quadro,
        t_s=discovery.t_s,
        distancia_cm=1.0,
        angulo_deg=0.0,
        details={},
    )
    scenario.events = [discovery]
    result = invoke(scenario)
    assert result.exit_code == 0, result.output
    report = json.loads(next(scenario.out.glob("*/sequence.json")).read_text(encoding="utf-8"))
    assert report["itens"] == []


def test_annotations_matching_agreement_exits_zero(scenario, tmp_path):
    scenario.events = [_entry_event(0, 1.0, discovery_t_s=0.5), _entry_event(1, 2.0, discovery_t_s=1.5)]
    d3 = _d3(tmp_path, [0, 1])
    result = invoke(scenario, "--annotations", d3)
    assert result.exit_code == 0, result.output
    comparison = json.loads(next(scenario.out.glob("*/comparacao.json")).read_text(encoding="utf-8"))
    assert comparison["agreement"] == 1.0
    assert comparison["status"] == "passed"


def test_annotations_below_threshold_exits_nonzero(scenario, tmp_path):
    scenario.events = [_entry_event(0, 1.0, discovery_t_s=0.5), _entry_event(1, 2.0, discovery_t_s=1.5)]
    d3 = _d3(tmp_path, [1, 0])
    result = invoke(scenario, "--annotations", d3)
    assert result.exit_code == 2, result.output
    comparison = json.loads(next(scenario.out.glob("*/comparacao.json")).read_text(encoding="utf-8"))
    assert comparison["agreement"] == 0.0
    assert comparison["status"] == "divergence_review_required"


def test_missing_annotations_file_is_blocked_not_fabricated(scenario, tmp_path):
    scenario.events = [_entry_event(0, 1.0, discovery_t_s=0.5)]
    result = invoke(scenario, "--annotations", tmp_path / "nao-existe.json")
    assert result.exit_code == 2, result.output
    comparison = json.loads(next(scenario.out.glob("*/comparacao.json")).read_text(encoding="utf-8"))
    assert comparison["status"] == "blocked_missing_d3"
    assert comparison["manual_sequence"] is None


def test_annotations_for_another_trial_is_rejected(scenario, tmp_path):
    scenario.events = [_entry_event(0, 1.0, discovery_t_s=0.5)]
    d3 = _d3(tmp_path, [0], trial_id=99)
    result = invoke(scenario, "--annotations", d3)
    assert result.exit_code != 0
    assert not list(scenario.out.glob("*/comparacao.json"))


def test_entry_recorded_before_dwell_existed_fails_with_a_clear_message_not_a_traceback(scenario):
    # details de uma entrada gravada por `barnes events enter` antes do US-14,
    # sem dwell_s/dwell_interpolado — reconstruir o EntryEvent não pode virar
    # um TypeError bruto sem mensagem (CalibrationCancelled... nao, ValueError).
    old_details = {
        "hole_number": 0,
        "quadro": 0,
        "t_s": 0.0,
        "confirmed_at_s": 0.2,
        "delta_latency": None,
        "delta_distance_cm": None,
        "total_latency": None,
        "total_distance_cm": None,
        "discovery_quadro": None,
        "discovery_t_s": None,
        "issues": [],
    }
    scenario.events = [
        HoleEvent(
            id=1,
            trial_id=7,
            hole_id=10,
            execucao_id=501,
            tipo="entrada",
            quadro=0,
            t_s=0.0,
            distancia_cm=None,
            angulo_deg=None,
            details=old_details,
        )
    ]
    result = invoke(scenario)
    assert result.exit_code == 1, result.output
    assert "Traceback" not in result.output
    assert "barnes events enter" in result.output
