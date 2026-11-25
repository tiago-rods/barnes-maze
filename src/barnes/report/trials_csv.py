from __future__ import annotations

from barnes.db.export import ExportContext, TrialIdentity
from barnes.metrics.displacement import compute_displacement
from barnes.metrics.latency import TargetEvent, compute_target_latencies, target_discovery
from barnes.report import MISSING, cm_to_m, with_missing_marker

TRIALS_CSV_COLUMNS = (
    "animal",
    "group",
    "day",
    "trial",
    "primary_latency",
    "primary_distance",
    "primary_event",
    "delta_latency",
    "delta_distance",
    "total_latency",
    "total_distance",
    "total_event",
)

TRIALS_CSV_EXTRA_COLUMNS = (
    "execucao_id",
    "path_distance",
    "mean_speed",
    "interpolated_fraction",
    "speed_time_base_approx",
    "pose_coverage",
)

TRIALS_CSV_ALL_COLUMNS = TRIALS_CSV_COLUMNS + TRIALS_CSV_EXTRA_COLUMNS


def build_trials_row(context: ExportContext, *, tempo_limite_s: float) -> dict:
    discovery = target_discovery(context.discoveries, context.target_hole_number)
    target_entries = [e for e in context.entries if e.hole_number == context.target_hole_number]
    entry_event = target_entries[0] if target_entries else None
    entry_target = (
        TargetEvent.ocorreu(entry_event.t_s) if entry_event is not None else TargetEvent.nao_ocorreu()
    )

    latencies = compute_target_latencies(
        context.trajectory, discovery, entry_target, tempo_limite_s=tempo_limite_s
    ).as_trials_csv()

    displacement = compute_displacement(context.trajectory).as_export_columns()
    pose_coverage = float(context.trajectory.column("pose_valida").to_numpy().mean())

    identity = context.identity
    row = {
        "animal": identity.animal,
        "group": identity.group_label,
        "day": identity.day_number,
        "trial": identity.trial_number_in_day,
        "primary_latency": latencies["primary_latency"],
        "primary_distance": cm_to_m(latencies["primary_distance"]),
        "primary_event": latencies["primary_event"],
        "delta_latency": entry_event.delta_latency if entry_event is not None else None,
        "delta_distance": cm_to_m(entry_event.delta_distance_cm) if entry_event is not None else None,
        "total_latency": latencies["total_latency"],
        "total_distance": cm_to_m(latencies["total_distance"]),
        "total_event": latencies["total_event"],
        "execucao_id": context.execucao_id,
        "path_distance": cm_to_m(displacement["path_distance"]),
        "mean_speed": cm_to_m(displacement["mean_speed"]),
        "interpolated_fraction": displacement["interpolated_fraction"],
        "speed_time_base_approx": displacement["speed_time_base_approx"],
        "pose_coverage": pose_coverage,
    }
    return with_missing_marker(row)


def missing_trials_row(identity: TrialIdentity) -> dict:
    row = {column: MISSING for column in TRIALS_CSV_ALL_COLUMNS}
    row["animal"] = identity.animal or MISSING
    row["group"] = identity.group_label or MISSING
    row["day"] = identity.day_number
    row["trial"] = identity.trial_number_in_day
    return row
