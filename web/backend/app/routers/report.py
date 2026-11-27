"""`POST /api/report/...` — exportação trials.csv/probes.csv no esquema do laboratório (US-25/26).

Mesma sequência que `cli_report.py`'s `trials`/`probes`/`set-group` já
executam — leitura de banco e escrita de CSV, nunca abre vídeo: sync, sem
job. `GET /api/report/download` serve o arquivo já escrito para o download
nativo do navegador.
"""

from __future__ import annotations

from pathlib import Path

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from barnes.db.export import (
    ExportError,
    list_trial_ids_by_phase,
    load_export_context,
    load_identity,
    set_experiment_group,
)
from barnes.metrics.latency import load_time_limit
from barnes.report import write_csv
from barnes.report.probes_csv import PROBES_CSV_ALL_COLUMNS, build_probes_row, missing_probes_row
from barnes.report.trials_csv import TRIALS_CSV_ALL_COLUMNS, build_trials_row, missing_trials_row

from ..deps import get_db
from ..schemas.report import (
    ExportProbesRequest,
    ExportResult,
    ExportTrialsRequest,
    Pendencia,
    SetGroupRequest,
)

router = APIRouter(prefix="/api/report", tags=["report"])


@router.post("/set-group", status_code=204)
def set_group(request: SetGroupRequest, conn: psycopg.Connection = Depends(get_db)) -> None:
    try:
        set_experiment_group(conn, request.experiment_id, request.group)
    except ExportError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/trials", response_model=ExportResult)
def export_trials(
    request: ExportTrialsRequest, conn: psycopg.Connection = Depends(get_db)
) -> ExportResult:
    limite = (
        request.tempo_limite_s
        if request.tempo_limite_s is not None
        else load_time_limit(Path(request.config))
    )
    rows: list[tuple[int, dict]] = []
    pendencias: list[Pendencia] = []
    trial_ids = [
        trial_id
        for phase in ("habituation", "acquisition")
        for trial_id in list_trial_ids_by_phase(conn, request.experiment_id, phase)
    ]
    for trial_id in trial_ids:
        try:
            context = load_export_context(conn, trial_id)
            row = build_trials_row(context, tempo_limite_s=limite)
        except ExportError as exc:
            pendencias.append(Pendencia(trial_id=trial_id, motivo=str(exc)))
            row = missing_trials_row(load_identity(conn, trial_id))
        rows.append((trial_id, row))

    out = Path(request.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for trial_id, row in rows:
        write_csv([row], out / f"trial_{trial_id}.csv", TRIALS_CSV_ALL_COLUMNS)
    destination = out / "trials.csv"
    write_csv([row for _, row in rows], destination, TRIALS_CSV_ALL_COLUMNS)
    return ExportResult(path=str(destination), count=len(rows), pendencias=pendencias)


@router.post("/probes", response_model=ExportResult)
def export_probes(
    request: ExportProbesRequest, conn: psycopg.Connection = Depends(get_db)
) -> ExportResult:
    rows: list[tuple[int, dict]] = []
    pendencias: list[Pendencia] = []
    trial_ids = list_trial_ids_by_phase(conn, request.experiment_id, "probe")
    for probe_number, trial_id in enumerate(trial_ids):
        try:
            context = load_export_context(conn, trial_id)
            row = build_probes_row(context, probe_number=probe_number)
        except ExportError as exc:
            pendencias.append(Pendencia(trial_id=trial_id, motivo=str(exc)))
            row = missing_probes_row(load_identity(conn, trial_id), probe_number=probe_number)
        rows.append((trial_id, row))

    out = Path(request.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for trial_id, row in rows:
        write_csv([row], out / f"probe_{trial_id}.csv", PROBES_CSV_ALL_COLUMNS)
    destination = out / "probes.csv"
    write_csv([row for _, row in rows], destination, PROBES_CSV_ALL_COLUMNS)
    return ExportResult(path=str(destination), count=len(rows), pendencias=pendencias)


@router.get("/download")
def download(path: str) -> FileResponse:
    file_path = Path(path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Arquivo não encontrado: {path}")
    return FileResponse(file_path, media_type="text/csv", filename=file_path.name)
