"""Orquestração local de entrada e calibração de eventos (US-12/13)."""

from __future__ import annotations

import csv
import json
import math
import platform
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import numpy as np
import pyarrow as pa
import typer
import yaml

from barnes.db.calibration import require_calibration
from barnes.db.connection import get_connection
from barnes.db.executions import get_execution, record_processing_execution
from barnes.db.hole_events import get_event_pose_quality, insert_hole_event, list_hole_events
from barnes.db.maze_configs import get_hole_ids, get_maze_config
from barnes.db.trials import StoredTrial, get_trial, get_trial_rotations
from barnes.events.calibration import (
    blocked_round,
    compare_events,
    load_manual_annotations,
    load_saved_round,
    render_evidence,
    save_round,
)
from barnes.events.discovery import DiscoveryEvent, detect_discoveries, load_discovery_params
from barnes.events.entry import EntryEvent, detect_entries, load_entry_params
from barnes.events.sequence import (
    SequenceItem,
    blocked_sequence_round,
    build_sequence,
    compare_sequence,
)
from barnes.geometry.holes import MazeGeometry
from barnes.geometry.reference_frame import require_rotations, target_hole_for_trial
from barnes.pose.dataset import file_sha256, git_revision_record
from barnes.pose.trajectory import read_metadata, read_trajectory
from barnes.provenance import (
    DEFAULT_THRESHOLDS_PATH,
    PACKAGE_DIR,
    GitState,
    ThresholdsSnapshot,
    thresholds_snapshot,
)


@dataclass(frozen=True)
class EventInputs:
    trial: StoredTrial
    table: pa.Table
    geometry: MazeGeometry
    cm_per_px: float
    hole_ids: dict[int, int]
    quality: dict
    trajectory_sha256: str
    target_hole_number: int | None


def _snapshot(config: Path) -> ThresholdsSnapshot:
    try:
        return thresholds_snapshot(config)
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML de limiares inválido: {config}.") from exc


def _same_number(value, expected) -> bool:
    """Metadados numéricos devem ser finitos; bool não equivale a 0/1."""
    if any(
        isinstance(number, bool) or not isinstance(number, int | float)
        for number in (value, expected)
    ):
        return False
    try:
        return (
            math.isfinite(value)
            and math.isfinite(expected)
            and math.isclose(value, expected, rel_tol=1e-10, abs_tol=1e-10)
        )
    except OverflowError:
        return False


def _load_inputs(trial_id: int, dsn: str | None, *, entry: bool) -> EventInputs:
    """Confere identidade, escala e recorte da série antes de recalcular eventos.

    A origem é o Parquet e sua execução, sem abrir/decodificar o vídeo (US-11
    RN04). A conferência física do vídeo pertence à geração da série de pose.
    """
    with get_connection(dsn) as conn:
        stored = get_trial(conn, trial_id)
        if stored.trajectory_path is None or stored.interval is None:
            raise ValueError(f"Trial #{trial_id}: gere a série com `barnes pose series` primeiro.")
        digest = file_sha256(stored.trajectory_path)
        table = read_trajectory(stored.trajectory_path)
        meta = read_metadata(table)
        geometry = get_maze_config(conn, stored.maze_config_id)
        calibration = require_calibration(conn, stored.maze_config_id)
        source = get_execution(conn, meta["execucao_id"])
        if (
            meta["trial_id"] != trial_id
            or meta["content_hash"] != stored.content_hash
            or source.trial_id != trial_id
            or source.maze_config_id != stored.maze_config_id
            or source.status != "concluido"
            or source.video_hash != stored.content_hash
        ):
            raise ValueError("A identidade da trajetória/execução não corresponde ao trial.")
        expected = {
            "cm_per_px": calibration.cm_per_px,
            "px_per_10cm": 10 / calibration.cm_per_px,
            "fps_real": stored.fps_real,
            "intervalo_inicio_s": stored.interval.start_s,
            "intervalo_fim_s": stored.interval.end_s,
        }
        if any(not _same_number(meta[k], v) for k, v in expected.items()):
            raise ValueError("Escala, FPS ou recorte incompatível; regenere a série de pose.")
        if meta["fps_variavel"] is not stored.fps_is_variable:
            raise ValueError("A informação de FPS variável difere da registrada no trial.")
        bounds = (source.parametros or {}).get("processed_interval_frames")
        if not isinstance(bounds, dict) or any(
            isinstance(bounds.get(key), bool) or not isinstance(bounds.get(key), int)
            for key in ("start", "end")
        ):
            raise ValueError("Execução sem os quadros originais da série; regenere a pose.")
        frames = table.column("quadro").to_numpy()
        if bounds["start"] < 0 or frames[0] != bounds["start"] or frames[-1] != bounds["end"]:
            raise ValueError("Trajetória incompleta: não cobre os quadros da execução original.")
        times = table.column("t_s").to_numpy()
        duration = stored.interval.end_s - stored.interval.start_s
        if times[0] < 0 or times[-1] > duration + 1e-10:
            raise ValueError("Trajetória contém tempos fora do intervalo útil do trial.")
        if not np.allclose(
            times, frames / stored.fps_real - stored.interval.start_s, rtol=0, atol=1e-10
        ):
            raise ValueError("Tempos da trajetória incompatíveis com os quadros/FPS do trial.")
        quality = get_event_pose_quality(conn, trial_id=trial_id)
        if quality["cobertura_execucao_id"] not in (None, meta["execucao_id"]):
            raise ValueError("Qualidade de pose pertence a outra execução; regenere a série.")
        target = None
        if entry:
            rotations = require_rotations(get_trial_rotations(conn, [trial_id]))
            target = target_hole_for_trial(geometry, rotation_deg=rotations[trial_id])
        return EventInputs(
            stored,
            table,
            geometry,
            calibration.cm_per_px,
            get_hole_ids(conn, stored.maze_config_id),
            quality,
            digest,
            target,
        )


def _detect(inputs: EventInputs, config: Path, *, entry: bool):
    params = load_discovery_params(config)
    if not math.isfinite(params.distance_cm) or not math.isfinite(params.angle_deg):
        raise ValueError("Os limiares de descoberta precisam ser finitos.")
    discoveries = detect_discoveries(inputs.table, inputs.geometry, inputs.cm_per_px, params)
    entries = []
    if entry:
        entries = detect_entries(
            inputs.table,
            inputs.geometry,
            inputs.cm_per_px,
            load_entry_params(config),
            discoveries,
            trial_id=inputs.trial.id,
            target_hole_number=inputs.target_hole_number,
        )
    return discoveries, entries


def _provenance(snapshot: ThresholdsSnapshot, inputs: EventInputs | None = None) -> dict:
    record = {
        "thresholds": {"path": snapshot.path, "values": snapshot.values},
        "hashes": {"config_sha256": snapshot.sha256},
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.node(),
            "packages": {name: version(name) for name in ("barnes", "numpy", "pyarrow")},
        },
        "source": git_revision_record(PACKAGE_DIR),
    }
    if inputs is not None:
        record.update(
            {
                "trial_id": inputs.trial.id,
                "maze_config_id": inputs.trial.maze_config_id,
                "trajectory": str(inputs.trial.trajectory_path),
                "trajectory_metadata": read_metadata(inputs.table),
                "geometry": asdict(inputs.geometry),
                "cm_per_px": inputs.cm_per_px,
                "target_hole_number_platform": inputs.target_hole_number,
                "pose_quality": inputs.quality,
                "video_verification": "identidade_da_serie_sem_reabrir_video",
            }
        )
        record["hashes"].update(
            {
                "trajectory_sha256": inputs.trajectory_sha256,
                "video_sha256": inputs.trial.content_hash,
            }
        )
    return record


def _unchanged(inputs: EventInputs, snapshot: ThresholdsSnapshot) -> None:
    if file_sha256(Path(snapshot.path)) != snapshot.sha256:
        raise ValueError("O YAML mudou durante o cálculo; repita a rodada.")
    if file_sha256(inputs.trial.trajectory_path) != inputs.trajectory_sha256:
        raise ValueError("A trajetória mudou durante o cálculo; repita a rodada.")


def _record(
    conn,
    inputs: EventInputs,
    snapshot: ThresholdsSnapshot,
    provenance: dict,
    discoveries: list[DiscoveryEvent],
    entries: list[EntryEvent],
    *,
    command: str,
    started_at: datetime,
    artifact_path: Path,
    report: dict,
) -> int:
    execution = record_processing_execution(
        conn,
        trial_id=inputs.trial.id,
        maze_config_id=inputs.trial.maze_config_id,
        parameters={
            "comando": command,
            "config": snapshot.path,
            "trajectory": str(inputs.trial.trajectory_path),
            "trajectory_sha256": inputs.trajectory_sha256,
        },
        thresholds=snapshot,
        git=GitState.from_record(provenance["source"]),
        video_hash=inputs.trial.content_hash,
        started_at=started_at,
        duration_seconds=(datetime.now(UTC) - started_at).total_seconds(),
        artifact_path=str(artifact_path),
        metadata={"provenance": provenance, "event_report": report},
    )
    for event in discoveries:
        insert_hole_event(
            conn,
            trial_id=inputs.trial.id,
            hole_id=inputs.hole_ids[event.hole_number],
            execucao_id=execution,
            tipo="descoberta",
            quadro=event.quadro,
            t_s=event.t_s,
            distancia_cm=event.distancia_cm,
            angulo_deg=event.angulo_deg,
        )
    for event in entries:
        insert_hole_event(
            conn,
            trial_id=inputs.trial.id,
            hole_id=inputs.hole_ids[event.hole_number],
            execucao_id=execution,
            tipo="entrada",
            quadro=event.quadro,
            t_s=event.t_s,
            details=asdict(event),
        )
    return execution


def _write_report_json(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False, allow_nan=False)


def _write_report_csv(path: Path, fields: list[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _export_entries(directory: Path, inputs: EventInputs, execution: int, entries, report) -> None:
    _write_report_json(directory / "events.json", {**report, "execucao_id": execution})
    fields = [
        "trial_id",
        "execucao_id",
        "hole_number_platform",
        "quadro",
        "t_s",
        "confirmed_at_s",
        "dwell_s",
        "dwell_interpolado",
        "discovery_t_s",
        "delta_latency",
        "delta_distance",
        "total_latency",
        "total_distance",
        "qualidade_pose",
        "issues",
    ]
    rows = (
        {
            "trial_id": inputs.trial.id,
            "execucao_id": execution,
            "hole_number_platform": entry.hole_number,
            "quadro": entry.quadro,
            "t_s": entry.t_s,
            "confirmed_at_s": entry.confirmed_at_s,
            "dwell_s": entry.dwell_s,
            "dwell_interpolado": entry.dwell_interpolado,
            "discovery_t_s": entry.discovery_t_s,
            "delta_latency": entry.delta_latency,
            "delta_distance": entry.delta_distance_cm,
            "total_latency": entry.total_latency,
            "total_distance": entry.total_distance_cm,
            "qualidade_pose": inputs.quality.get("qualidade") or "nao_avaliada",
            "issues": json.dumps(entry.issues, ensure_ascii=False),
        }
        for entry in entries
    )
    _write_report_csv(directory / "entries.csv", fields, rows)


def _load_sequence_entries(
    trial_id: int, dsn: str | None
) -> tuple[MazeGeometry, float, int, list[EntryEvent], int | None]:
    """Lê as entradas já persistidas da execução de eventos mais recente do trial (US-15).

    Não abre a trajetória nem a pose (RN03): só a montagem, a rotação e
    `evento_buraco`. Entradas de execuções antigas (recalibração) são
    ignoradas — a sequência nunca mistura rodadas diferentes.
    """
    with get_connection(dsn) as conn:
        stored = get_trial(conn, trial_id)
        geometry = get_maze_config(conn, stored.maze_config_id)
        rotations = require_rotations(get_trial_rotations(conn, [trial_id]))
        rotation_deg = rotations[trial_id]
        target = target_hole_for_trial(geometry, rotation_deg=rotation_deg)
        entradas = [e for e in list_hole_events(conn, trial_id=trial_id) if e.tipo == "entrada"]
    if not entradas:
        return geometry, rotation_deg, target, [], None
    execucao_id = max(event.execucao_id for event in entradas)
    try:
        entries = [
            EntryEvent(**{**event.details, "issues": tuple(event.details.get("issues", ()))})
            for event in entradas
            if event.execucao_id == execucao_id
        ]
    except TypeError as exc:
        raise ValueError(
            f"Trial {trial_id}: a execução #{execucao_id} tem entradas sem dwell (US-14). "
            "Rode `barnes events enter` de novo para regenerar os eventos com dwell."
        ) from exc
    return geometry, rotation_deg, target, entries, execucao_id


def _export_sequence(directory: Path, items: tuple[SequenceItem, ...], report: dict) -> None:
    _write_report_json(directory / "sequence.json", report)
    fields = [
        "ordem",
        "buraco_platform",
        "angulo_deg_room",
        "t_descoberta_s",
        "t_entrada_s",
        "dwell_s",
        "dwell_interpolado",
        "alvo",
        "issues",
    ]
    rows = (
        {
            "ordem": item.ordem,
            "buraco_platform": item.buraco_platform,
            "angulo_deg_room": item.angulo_deg_room,
            "t_descoberta_s": item.t_descoberta_s,
            "t_entrada_s": item.t_entrada_s,
            "dwell_s": item.dwell_s,
            "dwell_interpolado": item.dwell_interpolado,
            "alvo": item.alvo,
            "issues": json.dumps(item.issues, ensure_ascii=False),
        }
        for item in items
    )
    _write_report_csv(directory / "sequencia.csv", fields, rows)


def _warn_source(provenance: dict) -> None:
    if not GitState.from_record(provenance["source"]).reproducible:
        typer.echo("Aviso: código sem commit limpo; estado registrado para auditoria.", err=True)


def register_event_commands(events_app: typer.Typer, command_errors: Callable) -> None:
    """Registra comandos sem dependência circular com barnes.cli."""

    @events_app.command("enter")
    def enter(
        trial: Annotated[int, typer.Option(min=1, help="Id do trial.")],
        config: Annotated[
            Path, typer.Option(help="YAML com encontrar e entrar.")
        ] = DEFAULT_THRESHOLDS_PATH,
        out: Annotated[Path, typer.Option(help="Diretório de novas execuções.")] = Path(
            "data/events"
        ),
        dsn: Annotated[str | None, typer.Option(help="DSN; padrão BARNES_DATABASE_URL.")] = None,
    ) -> None:
        """Detecta entradas, sinaliza inconsistências e exporta hesitação (s e cm)."""
        started_at = datetime.now(UTC)
        with command_errors():
            # Recusa parâmetros C2 ausentes antes de consultar o banco.
            snapshot = _snapshot(config)
            load_entry_params(config)
            inputs = _load_inputs(trial, dsn, entry=True)
            discoveries, entries = _detect(inputs, config, entry=True)
            provenance = _provenance(snapshot, inputs)
            target = next((e for e in entries if e.hole_number == inputs.target_hole_number), None)
            issues = [issue for e in entries for issue in e.issues]
            report = {
                "schema_version": 1,
                "trial_id": trial,
                "created_at": started_at.isoformat(),
                "units": {"time": "s", "distance": "cm"},
                "time_origin": "intervalo_util",
                "pose_quality": inputs.quality,
                "status": "inconsistente" if issues else "calculado_sem_aceite_manual",
                "discoveries": [asdict(e) for e in discoveries],
                "entries": [asdict(e) for e in entries],
                "issues": issues,
                "target": {
                    "hole_number_platform": inputs.target_hole_number,
                    "total_event": target is not None,
                    "total_latency": target.total_latency if target else None,
                    "total_distance": target.total_distance_cm if target else None,
                    "delta_latency": target.delta_latency if target else None,
                    "delta_distance": target.delta_distance_cm if target else None,
                },
                "provenance": provenance,
            }
            _unchanged(inputs, snapshot)
            directory = out / f"entry-{uuid4().hex}"
            directory.mkdir(parents=True, exist_ok=False)
            try:
                with get_connection(dsn) as conn:
                    execution = _record(
                        conn,
                        inputs,
                        snapshot,
                        provenance,
                        discoveries,
                        entries,
                        command="events enter",
                        started_at=started_at,
                        artifact_path=directory,
                        report=report,
                    )
                    _export_entries(directory, inputs, execution, entries, report)
            except BaseException:
                for name in ("events.json", "entries.csv"):
                    (directory / name).unlink(missing_ok=True)
                directory.rmdir()
                raise
            _warn_source(provenance)
            typer.echo(f"Execução #{execution}: {len(entries)} entrada(s). Saída: {directory}")
            for issue in issues:
                typer.echo(f"Inconsistência: {issue}", err=True)
            if issues:
                raise typer.Exit(code=2)

    @events_app.command("sequence")
    def sequence(
        trial: Annotated[int, typer.Option(min=1, help="Id do trial.")],
        annotations: Annotated[
            Path | None, typer.Option(help="JSON D3 do observador treinado (RN04, opcional).")
        ] = None,
        out: Annotated[Path, typer.Option(help="Diretório de novas exportações.")] = Path(
            "data/events"
        ),
        dsn: Annotated[str | None, typer.Option(help="DSN; padrão BARNES_DATABASE_URL.")] = None,
    ) -> None:
        """Monta a sequência cronológica de checagens a partir do evento_buraco persistido."""
        with command_errors():
            geometry, rotation_deg, target, entries, execucao_id = _load_sequence_entries(
                trial, dsn
            )
            items = build_sequence(
                entries, geometry=geometry, rotation_deg=rotation_deg, target_hole_number=target
            )
            report = {
                "schema_version": 1,
                "trial_id": trial,
                "created_at": datetime.now(UTC).isoformat(),
                "units": {"time": "s", "angle": "deg_room"},
                "time_origin": "intervalo_util",
                "source_execucao_id": execucao_id,
                "itens": [asdict(item) for item in items],
            }
            comparison = None
            if annotations is not None:
                if not annotations.is_file():
                    comparison = blocked_sequence_round(trial)
                else:
                    manual = load_manual_annotations(annotations)
                    if manual.trial_id != trial:
                        raise ValueError("O trial de D3 difere de --trial.")
                    comparison = compare_sequence(
                        manual, [item.buraco_platform for item in items]
                    )
            directory = out / f"sequence-{uuid4().hex}"
            directory.mkdir(parents=True, exist_ok=False)
            try:
                _export_sequence(directory, items, report)
                if comparison is not None:
                    with (directory / "comparacao.json").open("x", encoding="utf-8") as stream:
                        json.dump(comparison, stream, indent=2, ensure_ascii=False, allow_nan=False)
            except BaseException:
                for name in ("sequence.json", "sequencia.csv", "comparacao.json"):
                    (directory / name).unlink(missing_ok=True)
                directory.rmdir()
                raise
            typer.echo(f"{len(items)} checagem(ns). Saída: {directory}")
            if comparison is not None:
                typer.echo(f"Concordância (RN04): {comparison['status']}")
                if not comparison["passed"]:
                    raise typer.Exit(code=2)

    @events_app.command("calibrate")
    def calibrate(
        trial: Annotated[
            int, typer.Option(min=1, help="Trial de referência anotado pelo laboratório.")
        ],
        kind: Annotated[
            str, typer.Option(help="descoberta (0,5 s) ou entrada (0,3 s).")
        ] = "descoberta",
        annotations: Annotated[
            Path | None, typer.Option(help="JSON D3 do observador treinado.")
        ] = None,
        config: Annotated[Path, typer.Option(help="YAML desta rodada.")] = DEFAULT_THRESHOLDS_PATH,
        out: Annotated[Path, typer.Option(help="Histórico de rodadas.")] = Path(
            "data/calibration/events"
        ),
        dsn: Annotated[str | None, typer.Option(help="DSN; padrão BARNES_DATABASE_URL.")] = None,
    ) -> None:
        """Compara com D3 e registra cada rodada; sem D3 registra bloqueio externo."""
        started_at = datetime.now(UTC)
        with command_errors():
            if kind not in {"descoberta", "entrada"}:
                raise ValueError("--kind deve ser descoberta ou entrada.")
            snapshot = _snapshot(config)
            if annotations is None or not annotations.is_file():
                report = blocked_round(trial_id=trial, kind=kind)
                paths = save_round(report, out, provenance=_provenance(snapshot))
                typer.echo(f"Bloqueado por D3: anotação não entregue. Registro: {paths[0]}")
                raise typer.Exit(code=2)
            annotation_hash = file_sha256(annotations)
            manual = load_manual_annotations(annotations)
            if manual.trial_id != trial:
                raise ValueError("O trial de D3 difere de --trial.")
            inputs = _load_inputs(trial, dsn, entry=kind == "entrada")
            if manual.video_sha256 is not None and manual.video_sha256 != inputs.trial.content_hash:
                raise ValueError("O hash do vídeo de D3 difere do trial.")
            duration = inputs.trial.interval.end_s - inputs.trial.interval.start_s
            if any(e.hole_number not in inputs.hole_ids or e.t_s > duration for e in manual.events):
                raise ValueError("D3 contém buraco inexistente ou tempo fora do intervalo útil.")
            discoveries, entries = _detect(inputs, config, entry=kind == "entrada")
            selected = discoveries if kind == "descoberta" else entries
            report = compare_events(
                manual,
                [{"tipo": kind, "hole_number": e.hole_number, "t_s": e.t_s} for e in selected],
                kind=kind,
            )
            issues = [issue for e in entries for issue in e.issues]
            report["consistency_issues"] = issues
            if issues:
                report["timing_status"] = report["status"]
                report["status"] = "divergence_review_required"
                report["passed"] = False
                report["next_action"] = (
                    "Revisar inconsistências D->E e lacunas na trajetória com o laboratório. "
                    "A coincidência temporal não resolve essas pendências. G3 segue pendente."
                )
            provenance = _provenance(snapshot, inputs)
            provenance["annotations"] = str(annotations)
            provenance["hashes"]["annotations_sha256"] = annotation_hash
            _unchanged(inputs, snapshot)
            if file_sha256(annotations) != annotation_hash:
                raise ValueError("D3 mudou durante o cálculo; repita a rodada.")
            paths = ()
            try:
                with get_connection(dsn) as conn:
                    execution = _record(
                        conn,
                        inputs,
                        snapshot,
                        provenance,
                        discoveries,
                        entries,
                        command="events calibrate",
                        started_at=started_at,
                        artifact_path=out,
                        report=report,
                    )
                    report["execucao_id"] = execution
                    paths = save_round(report, out, provenance=provenance)
            except BaseException:
                for path in paths:
                    path.unlink(missing_ok=True)
                raise
            _warn_source(provenance)
            typer.echo(f"Rodada: {paths[0]}\nEvidência: {paths[1]}\nResultado: {report['status']}")
            if report["status"] != "passed":
                typer.echo(
                    "Revisar a definição operacional com o laboratório; G3 continua pendente."
                )
                raise typer.Exit(code=2)

    @events_app.command("calibration-evidence")
    def evidence(
        round_file: Annotated[Path, typer.Argument(help="JSON de uma rodada registrada.")],
        document: Annotated[Path, typer.Option(help="Documento de G3.")] = Path(
            "docs/definicoes-metricas.md"
        ),
    ) -> None:
        """Acrescenta evidência da rodada ao documento, sem conceder aceite G3."""
        with command_errors():
            report = load_saved_round(round_file)
            rendered = render_evidence(report)
            current = document.read_text(encoding="utf-8")
            marker = f"<!-- calibration-round:{report['round_id']} -->"
            if marker in current:
                raise ValueError("Esta rodada já consta no documento.")
            addition = "\n\n" + marker + "\n" + rendered
            temporary = document.with_name(f".{document.name}.{uuid4().hex}.tmp")
            try:
                temporary.write_text(current + addition, encoding="utf-8")
                temporary.replace(document)
            finally:
                temporary.unlink(missing_ok=True)
            typer.echo(f"Evidência acrescentada a {document}. Aceite escrito G3 segue separado.")
