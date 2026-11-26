from __future__ import annotations

from dataclasses import dataclass

import psycopg
import pyarrow as pa

from barnes.db.hole_events import list_hole_events
from barnes.db.maze_configs import get_hole_ids, get_maze_config
from barnes.db.trials import get_trial
from barnes.events.discovery import DiscoveryEvent
from barnes.events.entry import EntryEvent
from barnes.geometry.holes import MazeGeometry
from barnes.geometry.reference_frame import target_hole_for_trial
from barnes.pose.trajectory import read_trajectory


class ExportError(ValueError):
    pass


@dataclass(frozen=True)
class TrialIdentity:
    trial_id: int
    animal: str | None
    group_label: str | None
    day_number: int
    trial_number_in_day: int
    phase: str


@dataclass(frozen=True)
class ExportContext:
    identity: TrialIdentity
    trajectory: pa.Table
    geometry: MazeGeometry
    rotation_deg: float
    target_hole_number: int
    discoveries: list[DiscoveryEvent]
    entries: list[EntryEvent]
    execucao_id: int


def load_identity(conn: psycopg.Connection, trial_id: int) -> TrialIdentity:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.name, e.group_label, t.day_number, t.trial_number_in_day, t.phase
            FROM trials t
            JOIN experiments e ON e.id = t.experiment_id
            LEFT JOIN subjects s ON s.experiment_id = t.experiment_id
            WHERE t.id = %s
            """,
            (trial_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise ExportError(f"Trial {trial_id}: não encontrado.")
    animal, group_label, day_number, trial_number_in_day, phase = row
    return TrialIdentity(trial_id, animal, group_label, day_number, trial_number_in_day, phase)


def load_export_context(conn: psycopg.Connection, trial_id: int) -> ExportContext:
    identity = load_identity(conn, trial_id)

    stored = get_trial(conn, trial_id)
    if stored.trajectory_path is None:
        raise ExportError(f"Trial {trial_id}: trajetória (US-09) ainda não gerada.")
    trajectory = read_trajectory(stored.trajectory_path)

    with conn.cursor() as cur:
        cur.execute("SELECT rotation_deg FROM trials WHERE id = %s", (trial_id,))
        (rotation_deg,) = cur.fetchone()
    if rotation_deg is None:
        raise ExportError(f"Trial {trial_id}: rotação da plataforma não registrada (US-05).")

    geometry = get_maze_config(conn, stored.maze_config_id)
    target_hole_number = target_hole_for_trial(geometry, rotation_deg=rotation_deg)
    hole_number_by_id = {hole_id: number for number, hole_id in get_hole_ids(conn, stored.maze_config_id).items()}

    all_events = list_hole_events(conn, trial_id=trial_id)
    entry_events = [event for event in all_events if event.tipo == "entrada"]
    if not entry_events:
        raise ExportError(f"Trial {trial_id}: eventos de entrada (US-13) ainda não calculados.")
    execucao_id = max(event.execucao_id for event in entry_events)

    entries = [
        EntryEvent(**{**event.details, "issues": tuple(event.details.get("issues", ()))})
        for event in entry_events
        if event.execucao_id == execucao_id
    ]
    discoveries = [
        DiscoveryEvent(
            hole_number=hole_number_by_id[event.hole_id],
            quadro=event.quadro,
            t_s=event.t_s,
            distancia_cm=event.distancia_cm,
            angulo_deg=event.angulo_deg,
        )
        for event in all_events
        if event.tipo == "descoberta" and event.execucao_id == execucao_id
    ]

    return ExportContext(
        identity=identity,
        trajectory=trajectory,
        geometry=geometry,
        rotation_deg=rotation_deg,
        target_hole_number=target_hole_number,
        discoveries=discoveries,
        entries=entries,
        execucao_id=execucao_id,
    )


def set_experiment_group(conn: psycopg.Connection, experiment_id: int, group_label: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE experiments SET group_label = %s WHERE id = %s", (group_label, experiment_id)
        )
        if cur.rowcount == 0:
            raise ExportError(f"Experimento {experiment_id}: não encontrado.")


def list_trial_ids_by_phase(
    conn: psycopg.Connection, experiment_id: int, phase: str
) -> list[int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM trials
            WHERE experiment_id = %s AND phase = %s
            ORDER BY day_number, trial_number_in_day
            """,
            (experiment_id, phase),
        )
        return [row[0] for row in cur.fetchall()]
