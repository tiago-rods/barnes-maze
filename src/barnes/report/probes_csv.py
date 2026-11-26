from __future__ import annotations

from barnes.db.export import ExportContext, TrialIdentity
from barnes.metrics.displacement import compute_displacement
from barnes.metrics.efficiency import compute_trial_route_efficiency
from barnes.metrics.latency import (
    DEFAULT_DISTANCE_POINT,
    TargetEvent,
    compute_target_latencies,
    target_discovery,
    travelled_distance_cm,
)
from barnes.report import MISSING, cm_to_m, with_missing_marker

PROBE_DURATION_S = 90.0

PROBES_CSV_COLUMNS = (
    "animal",
    "group",
    "probe",
    "primary_latency",
    "primary_distance",
    "total_latency",
    "total_distance",
)

PROBES_CSV_EXTRA_COLUMNS = (
    "execucao_id",
    "path_distance",
    "mean_speed",
    "interpolated_fraction",
    "speed_time_base_approx",
    "pose_coverage",
    "search_strategy",
    "entropy_bits",
    "primary_route_efficiency",
    "total_route_efficiency",
)

PROBES_CSV_ALL_COLUMNS = PROBES_CSV_COLUMNS + PROBES_CSV_EXTRA_COLUMNS


def build_probes_row(
    context: ExportContext, *, probe_number: int, ponto: str = DEFAULT_DISTANCE_POINT
) -> dict:
    discovery = target_discovery(context.discoveries, context.target_hole_number)
    t_s = context.trajectory.column("t_s").to_numpy()
    x_cm = context.trajectory.column(f"{ponto}_x_cm_image").to_numpy()
    y_cm = context.trajectory.column(f"{ponto}_y_cm_image").to_numpy()
    valid = context.trajectory.column(f"{ponto}_valido").to_numpy().astype(bool)

    if discovery.t_s is not None:
        primary_latency = discovery.t_s
    else:
        primary_latency = PROBE_DURATION_S
    primary_distance = travelled_distance_cm(t_s, x_cm, y_cm, valid, until_s=primary_latency)
    total_latency = PROBE_DURATION_S
    total_distance = travelled_distance_cm(t_s, x_cm, y_cm, valid, until_s=PROBE_DURATION_S)

    displacement = compute_displacement(context.trajectory).as_export_columns()
    pose_coverage = float(context.trajectory.column("pose_valida").to_numpy().mean())

    latencies_obj = compute_target_latencies(
        context.trajectory,
        discovery,
        TargetEvent.nao_ocorreu(),
        tempo_limite_s=PROBE_DURATION_S,
        ponto_distancia=ponto,
    )
    route_efficiency = compute_trial_route_efficiency(
        context.trajectory, latencies_obj, geometry=context.geometry, cm_per_px=context.cm_per_px
    ).as_trial_results()

    identity = context.identity
    row = {
        "animal": identity.animal,
        "group": identity.group_label,
        "probe": probe_number,
        "primary_latency": primary_latency,
        "primary_distance": cm_to_m(primary_distance),
        "total_latency": total_latency,
        "total_distance": cm_to_m(total_distance),
        "execucao_id": context.execucao_id,
        "path_distance": cm_to_m(displacement["path_distance"]),
        "mean_speed": cm_to_m(displacement["mean_speed"]),
        "interpolated_fraction": displacement["interpolated_fraction"],
        "speed_time_base_approx": displacement["speed_time_base_approx"],
        "pose_coverage": pose_coverage,
        "search_strategy": context.search_strategy,
        "entropy_bits": context.entropy_bits,
        "primary_route_efficiency": route_efficiency["primary_route_efficiency"],
        "total_route_efficiency": route_efficiency["total_route_efficiency"],
    }
    return with_missing_marker(row)


def missing_probes_row(identity: TrialIdentity, *, probe_number: int) -> dict:
    row = {column: MISSING for column in PROBES_CSV_ALL_COLUMNS}
    row["animal"] = identity.animal or MISSING
    row["group"] = identity.group_label or MISSING
    row["probe"] = probe_number
    return row
