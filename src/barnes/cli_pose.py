"""Orquestração dos comandos US-07/08: cálculo local e persistência separados."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated

import psycopg
import typer

from barnes.db.connection import get_connection
from barnes.db.maze_configs import get_maze_config
from barnes.db.pose_executions import get_inference_trial, list_executions, record_execution
from barnes.pose.annotations import AnnotatedFrame
from barnes.pose.dataset import load_dataset_manifest, prepare_dataset, write_json
from barnes.pose.environment import inspect_hardware, plan_training_location
from barnes.pose.evaluation import (
    evaluate_pose,
    finalize_evaluation_record,
    write_evaluation_report,
)
from barnes.pose.inference import (
    InferenceError,
    infer_trial,
    load_inference_record,
    load_inference_run_record,
    predict_test_set,
)
from barnes.pose.protocol import DEFAULT_CONFIG_PATH, load_annotation_protocol
from barnes.pose.split import ManifestRow
from barnes.pose.training import (
    DEFAULT_CONFIG,
    TrainingError,
    load_model_manifest,
    load_training_run_record,
    train_model,
)

DATA = Path("data/annotations")


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Esperado objeto JSON: {path}")  # noqa: TRY004
    return value


def _new_json(path: Path, document: dict) -> None:
    if path.exists():
        raise ValueError(
            f"Arquivo já existe: {path}. Escolha outro --out para preservar o registro."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, document)


def _record_local_run(run_dir: Path, kind: str, dsn: str | None) -> int:
    """Persiste artefatos já existentes; falha de banco nunca apaga o resultado local."""
    run_dir = run_dir.resolve()
    run = (
        load_training_run_record(run_dir)
        if kind == "treino"
        else load_inference_run_record(run_dir, kind)
    )
    with get_connection(dsn) as conn:
        identifier = record_execution(
            conn,
            kind=kind,
            model_id=run.document["model_id"],
            maze_config_id=run.document["maze_config_id"],
            trial_id=run.document.get("trial_id"),
            status="concluido" if run.document["status"] == "completed" else "falhou",
            metadata=run.document,
            duration_seconds=run.duration_seconds,
            artifact_path=str(run_dir / run.artifact_filename),
        )
    # Não altera o manifesto nem os hashes de pesos/configuração.
    write_json(run_dir / "registro-banco.json", {"execution_id": identifier, "kind": kind})
    return identifier


def _persist_or_explain(run_dir: Path, kind: str, dsn: str | None) -> int:
    try:
        return _record_local_run(run_dir, kind, dsn)
    except psycopg.Error:
        typer.echo(
            f"Artefatos preservados em {run_dir}. Banco indisponível; após recuperar, execute: "
            f'barnes pose register-run "{run_dir}" --kind {kind}',
            err=True,
        )
        raise


def register_pose_commands(app: typer.Typer, errors) -> None:
    """Acrescenta comandos à árvore `barnes pose`, mantendo os da US-06."""

    @app.command("hardware")
    def hardware(
        out: Annotated[Path, typer.Option(help="Um relatório por máquina do grupo.")] = Path(
            "data/pose/hardware.json"
        ),
    ) -> None:
        """Conferir NVIDIA/VRAM/RAM e registrar inventário sem instalar CUDA."""
        with errors():
            report = inspect_hardware()
            _new_json(out, report)
            typer.echo(f"Máquina: {report['machine']['hostname']} | relatório: {out}")
            typer.echo(f"RAM física: {(report['ram_bytes'] or 0) / 1e9:.2f} GB")
            for gpu in report["gpus"]:
                typer.echo(
                    f"GPU {gpu['index']}: {gpu['name']} | {gpu['memory_mib']} MiB | driver {gpu['driver_version']}"
                )
            if not report["eligible"]:
                for reason in report["reasons"]:
                    typer.echo(reason, err=True)
                raise typer.Exit(1)
            typer.echo("RAM/VRAM aprovadas. Compatibilidade CUDA será verificada antes do treino.")

    @app.command("plan-training")
    def plan_training(
        report: Annotated[
            list[Path], typer.Option("--report", help="Repita para todas as máquinas oferecidas.")
        ],
        out: Annotated[Path, typer.Option()] = Path("data/pose/plano-treino.json"),
        institutional: Annotated[
            str, typer.Option(help="sim, nao ou desconhecido")
        ] = "desconhecido",
        kaggle: Annotated[str, typer.Option(help="sim, nao ou desconhecido")] = "desconhecido",
        colab: Annotated[str, typer.Option(help="sim, nao ou desconhecido")] = "desconhecido",
        d4_reference: Annotated[
            str | None, typer.Option(help="Referência da resposta D4 explicitamente favorável.")
        ] = None,
    ) -> None:
        """Registrar prioridade grupo/instituição/Kaggle/Colab, sem upload."""
        with errors():
            availability = {"sim": True, "nao": False, "desconhecido": None}
            if any(value not in availability for value in (institutional, kaggle, colab)):
                raise ValueError("Disponibilidade aceita somente sim, nao ou desconhecido.")
            reports = [_read_json(path) for path in report]
            plan = plan_training_location(
                reports,
                availability[institutional],
                availability[kaggle],
                availability[colab],
                bool(d4_reference),
                d4_reference,
            )
            plan["group_reports"] = reports
            plan["availability"] = {
                "institucional": availability[institutional],
                "kaggle": availability[kaggle],
                "colab": availability[colab],
            }
            _new_json(out, plan)
            typer.echo(f"Plano: {plan['status']} | local: {plan['location']} | {out}")
            for reason in plan["reasons"]:
                typer.echo(reason)
            if plan["status"] != "selected":
                raise typer.Exit(1)

    @app.command("prepare-training")
    def prepare_training(
        maze_config_id: Annotated[int, typer.Option(min=1)],
        annotations: Annotated[Path, typer.Option()] = DATA / "anotacoes.csv",
        manifest: Annotated[Path, typer.Option()] = DATA / "divisao.csv",
        samples: Annotated[Path, typer.Option()] = DATA,
        out: Annotated[Path, typer.Option()] = Path("data/pose/datasets"),
    ) -> None:
        """Congelar PNGs rotulados, divisão e .slp em pacote versionado por conteúdo."""
        with errors():
            try:
                path = prepare_dataset(annotations, manifest, samples, out, maze_config_id)
            except ImportError as exc:
                raise RuntimeError(str(exc)) from exc
            typer.echo(f"Conjunto preparado: {path}")
            typer.echo("Somente quadros rotulados; nenhum vídeo original incluído ou enviado.")

    @app.command("train")
    def train(
        dataset: Annotated[Path, typer.Option(help="Pacote de prepare-training.")],
        config: Annotated[Path, typer.Option()] = DEFAULT_CONFIG,
        models: Annotated[Path, typer.Option()] = Path("models"),
        plan: Annotated[
            Path | None, typer.Option(help="Plano registrado; obrigatório para fallback.")
        ] = None,
        location: Annotated[
            str, typer.Option(help="grupo, institucional, kaggle ou colab")
        ] = "grupo",
        defer_db: Annotated[
            bool,
            typer.Option(
                "--defer-db",
                help="Treinar sem banco na máquina remota; registrar depois no laboratório.",
            ),
        ] = False,
        dsn: str = typer.Option(None, help="Postgres local; padrão BARNES_DATABASE_URL."),
    ) -> None:
        """Treinar um modelo por montagem e registrar pesos/hiperparâmetros em execucao."""
        with errors():
            if location not in {"grupo", "institucional", "kaggle", "colab"}:
                raise ValueError("Local de treino inválido.")
            chosen_plan = None if plan is None else _read_json(plan)
            if location != "grupo" and chosen_plan is None:
                raise ValueError(
                    "Fallback exige --plan com a escolha registrada por plan-training."
                )
            if chosen_plan is not None:
                saved_availability = chosen_plan.get("availability", {})
                checked_plan = plan_training_location(
                    chosen_plan.get("group_reports", []),
                    saved_availability.get("institucional"),
                    saved_availability.get("kaggle"),
                    saved_availability.get("colab"),
                    chosen_plan.get("d4_approved", False),
                    chosen_plan.get("d4_reference"),
                )
                if checked_plan["status"] != "selected" or checked_plan["location"] != location:
                    raise ValueError(
                        "Plano não autoriza o local solicitado; conclua o levantamento/D4."
                    )
            hardware_report = inspect_hardware()
            hardware_report.update(
                training_location=location,
                training_plan=chosen_plan,
                database_registration="deferred" if defer_db else "automatic",
            )
            if not hardware_report["eligible"]:
                raise ValueError("Treino bloqueado: " + " ".join(hardware_report["reasons"]))
            package = load_dataset_manifest(dataset)
            # Descobre erro de cadastro/migração antes de gastar horas de GPU.
            if not defer_db:
                with get_connection(dsn) as conn:
                    get_maze_config(conn, package["maze_config_id"])
                    list_executions(conn, model_id="preflight")
            typer.echo(
                "Treino iniciado. Progresso e erros serão preservados em models/<id>/training.log."
            )
            try:
                run_dir = train_model(dataset, models, config, hardware_report)
            except TrainingError as exc:
                if getattr(exc, "model_dir", None):
                    if defer_db:
                        typer.echo(
                            f"Tentativa preservada em {exc.model_dir}; registro no banco pendente."
                        )
                    else:
                        _persist_or_explain(exc.model_dir, "treino", dsn)
                raise
            if defer_db:
                typer.echo(f"Modelo: {run_dir} | registro em execucao PENDENTE.")
                typer.echo(f'No laboratório: barnes pose register-run "{run_dir}" --kind treino')
                return
            execution_id = _persist_or_explain(run_dir, "treino", dsn)
            typer.echo(f"Modelo: {run_dir} | execucao {execution_id}")

    @app.command("evaluate")
    def evaluate(
        model: Annotated[Path, typer.Option(help="Diretório models/<id> concluído.")],
        dataset: Annotated[Path, typer.Option(help="Mesmo conjunto congelado usado no treino.")],
        out: Annotated[Path, typer.Option()] = Path("data/pose/evaluations"),
        config: Annotated[Path, typer.Option()] = DEFAULT_CONFIG_PATH,
        device: Annotated[str, typer.Option()] = "cpu",
        batch_size: Annotated[int, typer.Option(min=1)] = 4,
        dsn: str = typer.Option(None, help="Postgres local; padrão BARNES_DATABASE_URL."),
    ) -> None:
        """Inferir teste e reportar erro global/centro/borda/buraco e aceite estrito."""
        with errors():
            package = load_dataset_manifest(dataset)
            model_record = load_model_manifest(model)
            if model_record["dataset_id"] != package["dataset_id"]:
                raise ValueError("Use o conjunto de teste congelado do modelo.")
            protocol = load_annotation_protocol(config)
            with get_connection(dsn) as conn:
                geometry = get_maze_config(conn, package["maze_config_id"])
                list_executions(conn, model_id="preflight")
            frames = [
                AnnotatedFrame(f["trial"], f["frame_index"], tuple(tuple(p) for p in f["points"]))
                for f in package["frames"]
            ]
            split = [
                ManifestRow(f["trial"], f["frame_index"], f["subset"]) for f in package["frames"]
            ]
            started = time.perf_counter()
            try:
                predictions, run_dir = predict_test_set(
                    model, dataset, out, device=device, batch_size=batch_size
                )
            except InferenceError as exc:
                if getattr(exc, "run_dir", None):
                    _persist_or_explain(exc.run_dir, "avaliacao", dsn)
                raise
            record = load_inference_record(run_dir)
            try:
                report = evaluate_pose(
                    frames,
                    predictions,
                    split,
                    {f.trial: geometry for f in frames},
                    protocol.regions,
                )
                report.update(
                    model_id=model_record["model_id"],
                    dataset_id=package["dataset_id"],
                    maze_config_id=package["maze_config_id"],
                )
                write_evaluation_report(report, run_dir)
                record["evaluation_accepted"] = report["accepted"]
            except (ValueError, OSError) as exc:
                record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
                raise
            finally:
                record = finalize_evaluation_record(run_dir, record, evaluation_started=started)
                if record["status"] == "failed":
                    _persist_or_explain(run_dir, "avaliacao", dsn)
            execution_id = _persist_or_explain(run_dir, "avaliacao", dsn)
            typer.echo(f"Relatório: {run_dir / 'avaliacao.md'} | execucao {execution_id}")
            if report["follow_up"]:
                typer.echo(f"Nova rodada US-06 solicitada localmente: {run_dir / 'us06-borda.md'}")
            if not report["accepted"]:
                typer.echo("Qualidade REPROVADA. Consulte erro por ponto e região.", err=True)
                raise typer.Exit(1)
            typer.echo(
                "Qualidade APROVADA. A validação offline na máquina do laboratório é separada."
            )

    @app.command("infer")
    def infer(
        model: Annotated[Path, typer.Option()],
        trial: Annotated[int, typer.Option(min=1)],
        video: Annotated[
            Path | None, typer.Option(help="Caminho local alternativo; hash deve coincidir.")
        ] = None,
        out: Annotated[Path, typer.Option()] = Path("data/pose/inference"),
        device: Annotated[str, typer.Option()] = "cpu",
        batch_size: Annotated[int, typer.Option(min=1)] = 4,
        dsn: str = typer.Option(None, help="Postgres local; padrão BARNES_DATABASE_URL."),
    ) -> None:
        """Inferir trial localmente, respeitando montagem, hash e intervalo cadastrado."""
        with errors():
            with get_connection(dsn) as conn:
                stored = get_inference_trial(conn, trial)
                list_executions(conn, model_id="preflight")
            try:
                run_dir = infer_trial(
                    model,
                    video or stored.filepath,
                    out,
                    trial_id=trial,
                    maze_config_id=stored.maze_config_id,
                    interval=stored.interval,
                    expected_content_hash=stored.content_hash,
                    fps=stored.fps_real,
                    frame_count=stored.frame_count,
                    width=stored.width_px,
                    height=stored.height_px,
                    device=device,
                    batch_size=batch_size,
                )
            except InferenceError as exc:
                if getattr(exc, "run_dir", None):
                    _persist_or_explain(exc.run_dir, "inferencia", dsn)
                raise
            execution_id = _persist_or_explain(run_dir, "inferencia", dsn)
            record = load_inference_record(run_dir)
            typer.echo(
                f"Pose: {run_dir / 'pose.csv'} | tempo: {record['duration_seconds']:.3f}s | execucao {execution_id}"
            )

    @app.command("register-run")
    def register_run(
        directory: Annotated[Path, typer.Argument()],
        kind: Annotated[str, typer.Option(help="treino, avaliacao ou inferencia")],
        dsn: str = typer.Option(None, help="Postgres local; padrão BARNES_DATABASE_URL."),
    ) -> None:
        """Registrar artefatos preservados após indisponibilidade do banco, sem reprocessar."""
        with errors():
            if kind not in {"treino", "avaliacao", "inferencia"}:
                raise ValueError("--kind deve ser treino, avaliacao ou inferencia.")
            identifier = _persist_or_explain(directory, kind, dsn)
            typer.echo(f"Registrado em execucao: {identifier}")

    @app.command("executions")
    def executions(
        trial: Annotated[int | None, typer.Option()] = None,
        model_id: Annotated[str | None, typer.Option()] = None,
        dsn: str = typer.Option(None, help="Postgres local; padrão BARNES_DATABASE_URL."),
    ) -> None:
        """Consultar execuções e seus registros completos de reprodutibilidade."""
        from dataclasses import asdict

        with errors(), get_connection(dsn) as conn:
            records = list_executions(conn, trial_id=trial, model_id=model_id)
            typer.echo(
                json.dumps(
                    [asdict(row) for row in records], default=str, ensure_ascii=False, indent=2
                )
            )
