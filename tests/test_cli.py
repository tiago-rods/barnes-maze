"""CLI integration for `scale`/`metrics` (US-02): real video decoding and Postgres;
only the mouse interaction (collect_segments) is mocked.

Requires BARNES_DATABASE_URL pointing at a Postgres with the schema applied;
skipped automatically otherwise (same convention as tests/db/).
"""

from __future__ import annotations

import json
import math
import os

import cv2
import numpy as np
import pytest
from typer.testing import CliRunner

from barnes import cli
from barnes.db.calibration import get_calibration
from barnes.db.connection import get_connection
from barnes.db.executions import get_execution
from barnes.db.pose_corrections import list_pose_corrections
from barnes.db.trial_results import get_trial_result
from barnes.db.trials import insert_trial
from barnes.io.calibration_ui import CalibrationCancelled
from barnes.io.trim import interval_from_seconds
from barnes.io.video import load_trial_video
from barnes.pose.dataset import file_sha256, git_revision_record
from barnes.pose.trajectory import read_metadata, read_trajectory
from barnes.provenance import PACKAGE_DIR, thresholds_snapshot

pytestmark = pytest.mark.skipif(
    not os.environ.get("BARNES_DATABASE_URL"),
    reason="Requer BARNES_DATABASE_URL apontando para um Postgres com o schema aplicado.",
)

runner = CliRunner()


def _write_video(path, size=(640, 480), frame_count=3):
    frame = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, size)
    assert writer.isOpened(), "O ambiente deve conseguir gravar o vídeo sintético mp4v."
    try:
        for _ in range(frame_count):
            writer.write(frame)
    finally:
        writer.release()


@pytest.fixture
def video(tmp_path):
    path = tmp_path / "reference.mp4"
    _write_video(path)
    return path


@pytest.fixture
def maze_config_id():
    """Cria user/experiment/maze_config num banco de teste real e comita.

    Precisa estar comitado (não só na transação do teste) porque os comandos
    de CLI abrem sua própria conexão via get_connection(dsn) — não veriam
    linhas ainda não comitadas por esta fixture. A limpeza por DELETE (em vez
    de rollback) é por isso: apagar o user em cascata leva experiment/
    maze_config/trial/trial_results com ele.
    """
    conn = get_connection()
    user_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (email, name) VALUES (%s, %s) RETURNING id",
                ("teste-cli@example.com", "Operador de teste"),
            )
            user_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO experiments (user_id, name) VALUES (%s, %s) RETURNING id",
                (user_id, "Experimento CLI"),
            )
            experiment_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO maze_configs
                    (experiment_id, name, arena_diameter_cm, hole_count, hole_diameter_cm)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (experiment_id, "montagem CLI", 90.0, 20, 5.0),
            )
            config_id = cur.fetchone()[0]
        conn.commit()
        yield config_id
    finally:
        if user_id is not None:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()
        conn.close()


def _insert_trial(maze_config_id, video, interval):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT experiment_id FROM maze_configs WHERE id = %s", (maze_config_id,))
            experiment_id = cur.fetchone()[0]
        result = insert_trial(
            conn,
            experiment_id=experiment_id,
            maze_config_id=maze_config_id,
            video=load_trial_video(video),
            phase="acquisition",
            day_number=1,
            trial_number_in_day=1,
            rotation_deg=0.0,
            interval=interval,
        )
        conn.commit()
        return result
    finally:
        conn.close()


@pytest.fixture
def trial_id(maze_config_id, video):
    # Intervalo útil de 0 s a 4 s: cobre as trajetórias dos testes (tempos 0, 2 e 4).
    # O vídeo sintético é mais curto, mas aqui só importa o intervalo gravado no trial.
    return _insert_trial(
        maze_config_id, video, interval_from_seconds(0.0, 4.0, 10.0, manually_adjusted=True)
    )


@pytest.fixture
def args(video, maze_config_id, monkeypatch):
    monkeypatch.setattr(
        cli,
        "collect_segments",
        lambda *args, **kwargs: (((10, 10), (210, 10)), ((10, 30), (10, 230))),
    )
    return ["--video", str(video), "--maze-config-id", str(maze_config_id)]


def calibrate(args, length="20"):
    result = runner.invoke(
        cli.app, ["scale", "calibrate", *args, "--length-1-cm", length, "--length-2-cm", length]
    )
    assert result.exit_code == 0, result.output + repr(result.exception)
    return result


def test_cli_full_flow_reuse_verification_and_recalibration(args, maze_config_id, trial_id, tmp_path, monkeypatch):
    output = calibrate(args)
    assert "0.1 cm/px" in output.output

    trajectory = tmp_path / "trajectory.csv"
    trajectory.write_text("x_px,y_px,time_s\n10,10,0\n40,50,2\n70,90,4\n", encoding="utf-8")
    result = runner.invoke(
        cli.app,
        [
            "metrics",
            "process",
            *args,
            "--trial",
            str(trial_id),
            "--trajectory",
            str(trajectory),
            "--ideal-distance-px",
            "80",
        ],
    )
    assert result.exit_code == 0, result.output + repr(result.exception)
    metrics = json.loads(result.stdout)
    assert metrics["distance_cm"] == pytest.approx(10)
    assert metrics["mean_speed_cm_s"] == pytest.approx(2.5)
    assert metrics["route_efficiency"] == pytest.approx(0.8)
    with get_connection() as conn:
        assert not get_trial_result(conn, trial_id).is_stale

    with monkeypatch.context() as scoped:
        # Só para esta chamada: scale verify pede 1 segmento, calibrate pede 2 (o mock
        # da fixture `args`) — sem escopar, o monkeypatch vazaria para a recalibração abaixo.
        scoped.setattr(cli, "collect_segments", lambda *a, **k: (((300, 100), (450, 100)),))
        checked = runner.invoke(cli.app, ["scale", "verify", *args, "--length-cm", "15"])
    assert checked.exit_code == 0, checked.output
    assert "Verificação aceita" in checked.output
    with get_connection() as conn:
        assert get_calibration(conn, maze_config_id).measured_error_pct == pytest.approx(0, abs=1)

    # O verify acima trocou a simulação por um segmento só; a calibração precisa de dois.
    monkeypatch.setattr(
        cli,
        "collect_segments",
        lambda *a, **k: (((10, 10), (210, 10)), ((10, 30), (10, 230))),
    )
    calibrate(args, length="40")  # recalibra a mesma montagem
    with get_connection() as conn:
        assert get_trial_result(conn, trial_id).is_stale  # calculado com a escala anterior

    reprocessed = runner.invoke(
        cli.app,
        ["metrics", "process", *args, "--trial", str(trial_id), "--trajectory", str(trajectory)],
    )
    assert reprocessed.exit_code == 0, reprocessed.output
    updated = json.loads(reprocessed.stdout)
    assert updated["distance_cm"] == pytest.approx(20)
    with get_connection() as conn:
        assert not get_trial_result(conn, trial_id).is_stale

    history = runner.invoke(cli.app, ["metrics", "executions"])
    assert history.exit_code == 0
    assert len(json.loads(history.stdout)) >= 1


def test_process_without_scale_fails_before_opening_video(maze_config_id, trial_id, monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("Sem calibração não deve decodificar o vídeo.")

    monkeypatch.setattr(cli, "read_frame", forbidden)
    result = runner.invoke(
        cli.app,
        [
            "metrics",
            "process",
            "--video",
            "missing.mp4",
            "--maze-config-id",
            str(maze_config_id),
            "--trial",
            str(trial_id),
            "--trajectory",
            "missing.csv",
        ],
    )
    assert result.exit_code == 2
    assert "exige calibração" in result.output


def _process(args, trial_id, trajectory):
    return runner.invoke(
        cli.app,
        ["metrics", "process", *args, "--trial", str(trial_id), "--trajectory", str(trajectory)],
    )


def test_process_ignores_samples_outside_useful_interval(args, trial_id, tmp_path):
    # US-03 RN02: a amostra em 10 s está depois do fim do intervalo (4 s) e não entra.
    calibrate(args)
    trajectory = tmp_path / "trajectory.csv"
    trajectory.write_text(
        "x_px,y_px,time_s\n10,10,0\n40,50,2\n70,90,4\n600,400,10\n", encoding="utf-8"
    )
    result = _process(args, trial_id, trajectory)
    assert result.exit_code == 0, result.output + repr(result.exception)
    metrics = json.loads(result.stdout)
    assert metrics["distance_cm"] == pytest.approx(10)
    assert metrics["samples_outside_interval"] == 1
    assert (metrics["interval_start_s"], metrics["interval_end_s"]) == (0.0, 4.0)


def test_process_refuses_scale_of_another_montagem(video, maze_config_id, trial_id, tmp_path):
    other = maze_config_id + 100_000  # qualquer id diferente da montagem do trial
    result = runner.invoke(
        cli.app,
        [
            "metrics", "process",
            "--video", str(video),
            "--maze-config-id", str(other),
            "--trial", str(trial_id),
            "--trajectory", str(tmp_path / "unused.csv"),
        ],
    )  # fmt: skip
    assert result.exit_code == 1
    assert f"montagem #{maze_config_id}" in result.output
    with get_connection() as conn:
        assert get_trial_result(conn, trial_id) is None


def test_process_refuses_trial_without_useful_interval(args, maze_config_id, tmp_path):
    calibrate(args)
    other_video = tmp_path / "sem_intervalo.mp4"
    _write_video(other_video, frame_count=5)  # outro conteúdo: content_hash é UNIQUE
    trial_without_interval = _insert_trial(maze_config_id, other_video, interval=None)
    result = _process(args, trial_without_interval, tmp_path / "unused.csv")
    assert result.exit_code == 1
    assert "intervalo útil" in result.output


def test_cancelled_calibration_creates_no_scale(args, maze_config_id, monkeypatch):
    def cancel(*args, **kwargs):
        raise CalibrationCancelled("Operação cancelada.")

    monkeypatch.setattr(cli, "collect_segments", cancel)
    result = runner.invoke(
        cli.app, ["scale", "calibrate", *args, "--length-1-cm", "20", "--length-2-cm", "20"]
    )
    assert result.exit_code == 130
    with get_connection() as conn:
        assert get_calibration(conn, maze_config_id) is None


def test_bad_recalibration_preserves_previous_scale_and_valid_results(args, maze_config_id, trial_id, tmp_path, monkeypatch):
    calibrate(args)
    trajectory = tmp_path / "trajectory.csv"
    trajectory.write_text("x_px,y_px,time_s\n10,10,0\n40,50,2\n70,90,4\n", encoding="utf-8")
    runner.invoke(
        cli.app,
        ["metrics", "process", *args, "--trial", str(trial_id), "--trajectory", str(trajectory)],
    )

    # Segundo segmento paralelo ao primeiro: calculate_calibration rejeita antes de persistir.
    monkeypatch.setattr(
        cli, "collect_segments", lambda *a, **k: (((10, 10), (210, 10)), ((10, 100), (210, 100)))
    )
    result = runner.invoke(
        cli.app, ["scale", "calibrate", *args, "--length-1-cm", "20", "--length-2-cm", "20"]
    )
    assert result.exit_code == 1
    assert "direções diferentes" in result.output

    with get_connection() as conn:
        assert get_calibration(conn, maze_config_id).cm_per_px == pytest.approx(0.1)
        assert not get_trial_result(conn, trial_id).is_stale


@pytest.mark.parametrize("content", ["x,y,time\n1,2,3", "x_px,y_px,time_s\n1,2,nope"])
def test_invalid_csv_is_reported_and_no_result_saved(args, maze_config_id, trial_id, tmp_path, content):
    calibrate(args)
    path = tmp_path / "bad.csv"
    path.write_text(content, encoding="utf-8")
    result = runner.invoke(
        cli.app,
        ["metrics", "process", *args, "--trajectory", str(path), "--trial", str(trial_id)],
    )
    assert result.exit_code == 1
    assert "Erro:" in result.output
    with get_connection() as conn:
        assert get_trial_result(conn, trial_id) is None


# --- US-27: proveniência registrada em cada `metrics process` -----------------


def _straight_trajectory(tmp_path):
    trajectory = tmp_path / "trajectory.csv"
    trajectory.write_text("x_px,y_px,time_s\n10,10,0\n40,50,2\n70,90,4\n", encoding="utf-8")
    return trajectory


def test_process_registers_execution_and_links_metric(args, trial_id, tmp_path):
    # Cenários 1 e 2: a execução guarda limiares, parâmetros e commit; a métrica aponta para ela.
    calibrate(args)
    result = _process(args, trial_id, _straight_trajectory(tmp_path))
    assert result.exit_code == 0, result.output + repr(result.exception)
    execucao_id = json.loads(result.stdout)["execucao_id"]

    with get_connection() as conn:
        assert get_trial_result(conn, trial_id).execucao_id == execucao_id
        stored = get_execution(conn, execucao_id)
    assert stored.kind == "processamento"
    assert stored.trial_id == trial_id
    assert stored.limiares_sha256 == thresholds_snapshot().sha256
    assert stored.limiares == thresholds_snapshot().values
    assert stored.parametros["trajectory_sha256"]
    assert stored.parametros["px_per_10cm"] == pytest.approx(100)
    assert stored.git_commit == git_revision_record(PACKAGE_DIR)["git_commit"]
    assert stored.recorded_at is not None

    shown = runner.invoke(cli.app, ["execution", "show", str(execucao_id)])
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.stdout)["limiares_sha256"] == stored.limiares_sha256


def test_process_marks_dirty_repository(args, trial_id, tmp_path, monkeypatch):
    # Cenário 4: alterações não commitadas → execução marcada como suja.
    calibrate(args)
    monkeypatch.setattr(
        cli, "git_revision_record", lambda _repo: {"git_commit": "d" * 40, "git_dirty": True}
    )
    result = _process(args, trial_id, _straight_trajectory(tmp_path))
    assert result.exit_code == 0, result.output
    assert "sujo" in result.stderr
    with get_connection() as conn:
        stored = get_execution(conn, json.loads(result.stdout)["execucao_id"])
    assert stored.git_dirty is True
    assert not stored.reproducible


def test_process_refuses_replaced_video(args, trial_id, video, tmp_path):
    # Cenário 3: conteúdo substituído no mesmo caminho → recusa, sem gravar nada.
    calibrate(args)
    _write_video(video, frame_count=7)
    result = _process(args, trial_id, _straight_trajectory(tmp_path))
    assert result.exit_code != 0
    assert f"trial #{trial_id}" in result.output
    with get_connection() as conn:
        assert get_trial_result(conn, trial_id) is None


def test_process_flags_moved_video_and_records_new_path(args, trial_id, video, tmp_path):
    # Cenário 3: mesmo conteúdo em outro caminho → processa, mas sinaliza e registra.
    calibrate(args)
    moved = tmp_path / "outra_pasta" / "renomeado.mp4"
    moved.parent.mkdir()
    video.rename(moved)
    moved_args = ["--video", str(moved), *args[2:]]
    result = _process(moved_args, trial_id, _straight_trajectory(tmp_path))
    assert result.exit_code == 0, result.output
    assert "Aviso" in result.stderr
    with get_connection() as conn:
        stored = get_execution(conn, json.loads(result.stdout)["execucao_id"])
    assert stored.parametros["video_movido"] is True
    assert stored.parametros["video"] == str(moved)


def test_catalog_list_flags_moved_video_by_trial(trial_id, video, tmp_path):
    # Cenário 3 pela CLI: o catálogo sinaliza a divergência e identifica o trial.
    listed = runner.invoke(cli.app, ["catalog", "list", "--json"])
    assert listed.exit_code == 0, listed.output
    row = next(r for r in json.loads(listed.stdout) if r["trial_id"] == trial_id)
    assert (row["situacao"], row["arquivo"]) == ("carregado", "presente")

    destination = tmp_path / "movidos"
    destination.mkdir()
    video.rename(destination / "renomeado.mp4")
    moved = runner.invoke(
        cli.app, ["catalog", "list", "--procurar-em", str(destination)]
    )
    assert moved.exit_code == 0, moved.output
    assert f"Divergência no trial #{trial_id}" in moved.stderr
    assert "renomeado.mp4" in moved.stderr
    assert f"#{trial_id}" in moved.stdout


# --- US-09: `pose series` gera a trajetória no contrato -----------------------


def _fake_inference_run(root, *, trial_id, maze_config_id, content_hash, fps, frames,
                        missing_snout=()):
    """Diretório de `pose infer` com registro e pose.csv verificáveis (hashes reais).

    O animal anda para a direita (θ = 0°), 4 px por quadro, focinho em x + 20 e
    y = 240; `missing_snout` lista quadros sem focinho.
    """
    root.mkdir(parents=True)
    header = ["trial", "quadro", "time_s"] + [
        f"{p}_{s}" for p in ("focinho", "centro_corpo", "base_cauda")
        for s in ("x_image", "y_image", "confidence")
    ]
    lines = [",".join(header)]
    for frame in range(frames[0], frames[1] + 1):
        x = 100.0 + 4 * frame
        snout = ["", "", ""] if frame in missing_snout else [x + 20, 240.0, 0.9]
        values = [*snout, x, 240.0, 0.8, x - 20, 240.0, 0.7]
        lines.append(",".join(map(str, ["abc", frame, frame / fps, *values])))
    (root / "pose.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    record = {
        "schema_version": 1, "status": "completed", "kind": "inferencia",
        "model_id": "sleap-maze-test", "dataset_id": "ds-test", "maze_config_id": maze_config_id,
        "trial_id": trial_id, "content_hash": content_hash, "fps": fps,
        "processed_interval_frames": {"start": frames[0], "end": frames[1]},
        "duration_seconds": 0.5, "artifacts": {"pose.csv": file_sha256(root / "pose.csv")},
    }
    (root / "execucao.json").write_text(json.dumps(record), encoding="utf-8")
    return root


def _trial_row(trial_id):
    with get_connection() as conn:
        return conn.execute(
            "SELECT maze_config_id, content_hash, fps_real, trajectory_path FROM trials "
            "WHERE id = %s", (trial_id,)
        ).fetchone()


def _series_args(run, trial_id, out):
    return ["pose", "series", "--trial", str(trial_id), "--inference", str(run), "--out", str(out)]


def test_pose_series_writes_contract_parquet_and_registers_execution(args, trial_id, tmp_path):
    # US-09 Cenário 1: Parquet com uma linha por quadro do intervalo útil (0..4 s a 10 fps =
    # quadros 0..40), x/y em cm, θ em graus, t em segundos. US-10: o quadro 7 sem focinho
    # (lacuna curta) é interpolado e marcado; a lacuna longa 20..27 fica ausente (US-09
    # Cenário 3) e é sinalizada para revisão; a cobertura vai para o trial.
    calibrate(args)  # 10 px por cm
    maze, digest, fps, _ = _trial_row(trial_id)
    missing = {7, *range(20, 28)}
    run = _fake_inference_run(tmp_path / "run", trial_id=trial_id, maze_config_id=maze,
                              content_hash=digest, fps=fps, frames=(0, 40), missing_snout=missing)
    result = runner.invoke(cli.app, _series_args(run, trial_id, tmp_path / "interim"))
    assert result.exit_code == 0, result.output + repr(result.exception)

    path = tmp_path / "interim" / f"trial_{trial_id}.parquet"
    table = read_trajectory(path)
    data, meta = table.to_pydict(), read_metadata(table)
    assert data["quadro"] == list(range(41))
    assert data["t_s"][-1] == pytest.approx(4.0)
    assert data["centro_corpo_x_cm_image"][0] == pytest.approx(10.0)  # 100 px / 10
    assert data["theta_deg_image"][0] == pytest.approx(0.0)
    # Lacuna curta: preenchida e marcada (US-10 Cenário 1).
    assert data["interpolado"][7] is True and data["pose_valida"][7] is True
    assert data["focinho_x_cm_image"][7] == pytest.approx((100 + 4 * 7 + 20) / 10)
    assert data["theta_deg_image"][7] == pytest.approx(0.0)
    # Lacuna longa: ausente, sem repetir o quadro anterior (US-09 Cenário 3).
    assert not any(data["interpolado"][20:28])
    assert not any(data["pose_valida"][20:28])
    assert math.isnan(data["theta_deg_image"][20])
    assert sum(data["interpolado"]) == 1

    execucao_id = meta["execucao_id"]
    assert set(data["execucao_id"]) == {execucao_id}
    report = meta["pos_processamento"]
    assert report["trechos_sinalizados"] == [
        {"inicio": 20, "fim": 27, "pontos": ["focinho"], "pendente": True}
    ]
    with get_connection() as conn:
        stored = get_execution(conn, execucao_id)
        coverage = conn.execute(
            "SELECT cobertura_pose, cobertura_execucao_id FROM trials WHERE id = %s",
            (trial_id,),
        ).fetchone()
    assert stored.kind == "processamento"
    assert stored.model_id == "sleap-maze-test"
    assert stored.artifact_path == str(path)
    assert stored.parametros["inference_run_id"] == "run"
    assert stored.parametros["pos_processamento"]["lacuna_curta_max_quadros"] == 5
    assert stored.metadata["qualidade_pose"]["qualidade"] == "revisao_pendente"
    assert _trial_row(trial_id)[3] == str(path)
    assert coverage == (pytest.approx(33 / 41), execucao_id)
    assert f"barnes pose review --trial {trial_id}" in result.stderr


def test_pose_series_refuses_inference_of_another_trial(args, trial_id, tmp_path):
    calibrate(args)
    maze, digest, fps, _ = _trial_row(trial_id)
    run = _fake_inference_run(tmp_path / "run", trial_id=trial_id + 1, maze_config_id=maze,
                              content_hash=digest, fps=fps, frames=(0, 40))
    result = runner.invoke(cli.app, _series_args(run, trial_id, tmp_path / "interim"))
    assert result.exit_code != 0
    assert f"#{trial_id + 1}" in result.output
    assert not (tmp_path / "interim").exists()


def test_pose_series_refuses_pose_of_other_video_content(args, trial_id, tmp_path):
    calibrate(args)
    maze, _, fps, _ = _trial_row(trial_id)
    run = _fake_inference_run(tmp_path / "run", trial_id=trial_id, maze_config_id=maze,
                              content_hash="0" * 64, fps=fps, frames=(0, 40))
    result = runner.invoke(cli.app, _series_args(run, trial_id, tmp_path / "interim"))
    assert result.exit_code != 0
    assert "hash" in result.output


def test_pose_series_without_scale_is_refused(trial_id, tmp_path):
    maze, digest, fps, _ = _trial_row(trial_id)
    run = _fake_inference_run(tmp_path / "run", trial_id=trial_id, maze_config_id=maze,
                              content_hash=digest, fps=fps, frames=(0, 40))
    result = runner.invoke(cli.app, _series_args(run, trial_id, tmp_path / "interim"))
    assert result.exit_code == 2
    assert "calibração" in result.output


def test_pose_series_carries_variable_fps_warning_to_outputs(args, trial_id, tmp_path):
    # SCRUM-118: fps variável da US-01 → aviso no terminal, no arquivo e no catálogo.
    calibrate(args)
    with get_connection() as conn:
        conn.execute("UPDATE trials SET fps_is_variable = TRUE WHERE id = %s", (trial_id,))
    maze, digest, fps, _ = _trial_row(trial_id)
    run = _fake_inference_run(tmp_path / "run", trial_id=trial_id, maze_config_id=maze,
                              content_hash=digest, fps=fps, frames=(0, 40))
    result = runner.invoke(cli.app, _series_args(run, trial_id, tmp_path / "interim"))
    assert result.exit_code == 0, result.output
    assert "fps variável" in result.stderr

    table = read_trajectory(tmp_path / "interim" / f"trial_{trial_id}.parquet")
    assert all(table.column("fps_variavel").to_pylist())
    assert read_metadata(table)["fps_variavel"] is True

    listed = runner.invoke(cli.app, ["catalog", "list", "--json", "--sem-arquivo"])
    row = next(r for r in json.loads(listed.stdout) if r["trial_id"] == trial_id)
    assert row["fps_variavel"] is True
    assert row["trajetoria"].endswith(f"trial_{trial_id}.parquet")


# --- US-10: revisão dos trechos sinalizados e qualidade nas saídas -------------


def _snout_px(frame):
    """Onde `_fake_inference_run` poria o focinho no quadro: o que o operador marcaria."""
    return 100.0 + 4 * frame + 20, 240.0


def _review(trial_id, monkeypatch, act):
    """Roda `pose review` com a janela simulada: `act(session, overlay)` faz a revisão."""
    seen = {}

    def fake_collect_review(frames, session, *, overlay=None, **kwargs):
        seen["start"] = (session.segment.start_frame, session.segment.end_frame, session.frame)
        seen["overlay"] = overlay
        act(session)
        return session.result()

    monkeypatch.setattr(cli, "collect_review", fake_collect_review)
    result = runner.invoke(cli.app, ["pose", "review", "--trial", str(trial_id)])
    return result, seen


def _catalog_row(trial_id):
    listed = runner.invoke(cli.app, ["catalog", "list", "--json", "--sem-arquivo"])
    assert listed.exit_code == 0, listed.output
    return next(r for r in json.loads(listed.stdout) if r["trial_id"] == trial_id)


def test_pose_review_goes_to_flagged_segment_and_records_corrections(
    args, trial_id, tmp_path, monkeypatch
):
    # Cenário 2: lacuna longa (focinho 20..27) → a revisão abre direto no trecho, o
    # operador marca dois quadros e a intervenção fica registrada na execução.
    calibrate(args)
    maze, digest, fps, _ = _trial_row(trial_id)
    run = _fake_inference_run(tmp_path / "run", trial_id=trial_id, maze_config_id=maze,
                              content_hash=digest, fps=fps, frames=(0, 40),
                              missing_snout=set(range(20, 28)))
    series = runner.invoke(cli.app, _series_args(run, trial_id, tmp_path / "interim"))
    assert series.exit_code == 0, series.output + repr(series.exception)
    assert _catalog_row(trial_id)["qualidade_pose"] == "revisao_pendente"

    def act(session):
        for frame in (22, 25):  # marcações esparsas; os vãos curtos são interpolados
            while session.frame < frame:
                session.next_frame()
            session.mark(*_snout_px(frame))
        session.confirm_segment()

    result, seen = _review(trial_id, monkeypatch, act)
    assert result.exit_code == 0, result.output + repr(result.exception)
    assert seen["start"] == (20, 27, 20)  # RN04: direto no trecho sinalizado
    assert seen["overlay"][20]["centro_corpo"] == pytest.approx((180.0, 240.0))  # em px
    assert "Revisão registrada na execução" in result.stdout

    path = tmp_path / "interim" / f"trial_{trial_id}.parquet"
    table = read_trajectory(path)
    data, meta = table.to_pydict(), read_metadata(table)
    review_id = meta["execucao_id"]
    assert all(data["pose_valida"][20:28])
    assert data["focinho_x_cm_image"][22] == pytest.approx(_snout_px(22)[0] / 10)
    assert [data["interpolado"][f] for f in range(20, 28)] == [
        True, True, False, True, True, False, True, True
    ]
    with get_connection() as conn:
        stored = get_execution(conn, review_id)
        corrections = list_pose_corrections(conn, trial_id)
        coverage = conn.execute(
            "SELECT cobertura_pose, cobertura_execucao_id FROM trials WHERE id = %s",
            (trial_id,),
        ).fetchone()
    assert stored.kind == "processamento"
    assert stored.parametros["comando"] == "pose review"
    assert stored.parametros["trechos_revisados"] == [{"inicio": 20, "fim": 27}]
    assert stored.parametros["correcoes_novas"] == 2
    assert stored.metadata["qualidade_pose"]["quadros_corrigidos"] == 2
    assert [(c.execucao_id, c.quadro, c.ponto) for c in corrections] == [
        (review_id, 22, "focinho"), (review_id, 25, "focinho")
    ]
    assert coverage == (pytest.approx(1.0), review_id)
    assert _catalog_row(trial_id)["qualidade_pose"] == "suficiente"

    # Regenerar a série reaplica as correções do banco: o resultado não depende da janela.
    again = runner.invoke(cli.app, _series_args(run, trial_id, tmp_path / "interim"))
    assert again.exit_code == 0, again.output
    assert all(read_trajectory(path).column("pose_valida").to_pylist()[20:28])
    assert _catalog_row(trial_id)["qualidade_pose"] == "suficiente"
    nothing = runner.invoke(cli.app, ["pose", "review", "--trial", str(trial_id)])
    assert nothing.exit_code == 0 and "Nenhum trecho pendente" in nothing.stdout


def test_pose_review_cancelled_saves_nothing(args, trial_id, tmp_path, monkeypatch):
    calibrate(args)
    maze, digest, fps, _ = _trial_row(trial_id)
    run = _fake_inference_run(tmp_path / "run", trial_id=trial_id, maze_config_id=maze,
                              content_hash=digest, fps=fps, frames=(0, 40),
                              missing_snout=set(range(20, 28)))
    assert runner.invoke(cli.app, _series_args(run, trial_id, tmp_path / "interim")).exit_code == 0

    def cancel(frames, session, **kwargs):
        session.mark(1.0, 1.0)
        raise cli.ReviewCancelled("Revisão cancelada; nenhuma correção foi gravada.")

    monkeypatch.setattr(cli, "collect_review", cancel)
    result = runner.invoke(cli.app, ["pose", "review", "--trial", str(trial_id)])
    assert result.exit_code == 130
    with get_connection() as conn:
        assert list_pose_corrections(conn, trial_id) == []
    assert _catalog_row(trial_id)["qualidade_pose"] == "revisao_pendente"


def test_pose_review_requires_a_series(trial_id):
    result = runner.invoke(cli.app, ["pose", "review", "--trial", str(trial_id)])
    assert result.exit_code == 1
    assert "pose series" in result.output


def test_trial_below_coverage_after_review_is_marked_in_outputs(
    args, maze_config_id, tmp_path, monkeypatch
):
    # Cenário 3: 7 quadros sem focinho em 100, revisados sem correção (animal fora de
    # vista) → cobertura 0,93 → qualidade insuficiente no catálogo e nas métricas.
    calibrate(args)
    other_video = tmp_path / "trial_100_quadros.mp4"
    _write_video(other_video, frame_count=5)  # outro conteúdo, outro hash
    trial = _insert_trial(
        maze_config_id, other_video, interval_from_seconds(0.0, 9.9, 10.0, manually_adjusted=True)
    )
    maze, digest, fps, _ = _trial_row(trial)
    run = _fake_inference_run(tmp_path / "run", trial_id=trial, maze_config_id=maze,
                              content_hash=digest, fps=fps, frames=(0, 99),
                              missing_snout=set(range(40, 47)))
    assert runner.invoke(cli.app, _series_args(run, trial, tmp_path / "interim")).exit_code == 0

    result, _ = _review(trial, monkeypatch, lambda session: session.confirm_segment())
    assert result.exit_code == 0, result.output + repr(result.exception)
    assert "QUALIDADE INSUFICIENTE" in result.stderr

    row = _catalog_row(trial)
    assert row["cobertura_pose"] == pytest.approx(0.93)
    assert row["qualidade_pose"] == "insuficiente"

    video_args = ["--video", str(other_video), "--maze-config-id", str(maze_config_id)]
    processed = _process(video_args, trial, _straight_trajectory(tmp_path))
    assert processed.exit_code == 0, processed.output + repr(processed.exception)
    assert "INSUFICIENTE" in processed.stderr
    output = json.loads(processed.stdout)
    assert (output["cobertura_pose"], output["qualidade_pose"]) == (
        pytest.approx(0.93), "insuficiente"
    )
    exported = runner.invoke(cli.app, ["metrics", "executions", "--trial", str(trial)])
    assert exported.exit_code == 0, exported.output
    (metric,) = json.loads(exported.stdout)
    assert (metric["cobertura_pose"], metric["qualidade_pose"]) == (
        pytest.approx(0.93), "insuficiente"
    )
