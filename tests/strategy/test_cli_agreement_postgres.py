"""`barnes strategy split/agreement/agreement-history` (US-21) com PostgreSQL real.

Rótulos sintéticos: provam que o rótulo automático vem do resultado mais recente
do `strategy classify` (não da linha atual de `trial_results`), que trials sem
classificação válida ficam fora com motivo, e que limiares divergentes são
recusados. Requer BARNES_TEST_DATABASE_URL migrado até a 0011.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from barnes import cli
from barnes.db.calibration import save_calibration
from barnes.db.connection import get_connection
from barnes.db.executions import record_processing_execution
from barnes.db.maze_configs import insert_maze_config
from barnes.db.trial_results import insert_trial_result
from barnes.geometry.holes import generate_holes
from barnes.io.calibration import Segment, calculate_calibration
from barnes.pose.dataset import file_sha256, git_revision_record
from barnes.provenance import PACKAGE_DIR, GitState, thresholds_snapshot
from barnes.strategy.agreement import Partition, write_partition

pytestmark = pytest.mark.skipif(
    not os.environ.get("BARNES_DATABASE_URL"),
    reason="Requer BARNES_TEST_DATABASE_URL e migrações até 0011 aplicadas.",
)
runner = CliRunner()
LIMIARES = {
    "cruzamentos_centro_min": 1,
    "adjacencia_angular_graus": 18.0,
    "erros_ate_alvo_max": 3,
    "centro_zona_raio_frac": 0.5,
    "serial_min_buracos": 2,
}


@pytest.fixture
def lab(tmp_path):
    user_id = None
    try:
        with get_connection() as conn:
            user_id = conn.execute(
                "INSERT INTO users(email, name) VALUES(%s, 'Synthetic US21') RETURNING id",
                (f"{uuid4()}@example.test",),
            ).fetchone()[0]
            experiment_id = conn.execute(
                "INSERT INTO experiments(user_id, name) VALUES(%s, 'Synthetic') RETURNING id",
                (user_id,),
            ).fetchone()[0]
            geometry = generate_holes(
                center_x_px=200,
                center_y_px=150,
                platform_radius_px=100,
                hole_count=8,
                start_angle_deg=0,
                target_hole_number=0,
                hole_radius_px=5,
            )
            maze_id = insert_maze_config(
                conn,
                experiment_id=experiment_id,
                name="Synthetic US21",
                arena_diameter_cm=20,
                hole_diameter_cm=1,
                geometry=geometry,
            )
            save_calibration(
                conn,
                maze_id,
                calculate_calibration(
                    [Segment((0, 0), (100, 0), 10), Segment((0, 0), (0, 100), 10)]
                ),
                reference_video="synthetic.mp4",
                reference_frame=0,
                reference_size=(400, 300),
            )
            px_per_10cm = conn.execute(
                "SELECT px_per_10cm FROM maze_configs WHERE id=%s", (maze_id,)
            ).fetchone()[0]

        def add_trial():
            with get_connection() as conn:
                return conn.execute(
                    """
                    INSERT INTO trials (experiment_id, maze_config_id, filename, filepath,
                        phase, day_number, trial_number_in_day, content_hash, width_px,
                        height_px, fps_declared, fps_real, frame_count, duration_s,
                        start_time_seconds, end_time_seconds, rotation_deg)
                    VALUES (%s,%s,'synthetic.mp4','no-video.mp4','acquisition',1,1,%s,400,300,
                        10,10,9,0.9,0,0.8,0) RETURNING id
                    """,
                    (experiment_id, maze_id, uuid4().hex + uuid4().hex),
                ).fetchone()[0]

        def add_result(
            trial_id, categoria, *, comando="strategy classify", limiares=None, px_used=None
        ):
            with get_connection() as conn:
                execucao_id = record_processing_execution(
                    conn,
                    trial_id=trial_id,
                    maze_config_id=maze_id,
                    parameters={"comando": comando},
                    thresholds=thresholds_snapshot(),
                    git=GitState.from_record(git_revision_record(PACKAGE_DIR)),
                    video_hash="hash",
                    started_at=datetime.now(UTC),
                    metadata={"estrategia": {"limiares": limiares or LIMIARES}},
                )
                insert_trial_result(
                    conn,
                    trial_id,
                    execucao_id=execucao_id,
                    distance_cm=None,
                    speed_mean_cm=None,
                    route_efficiency=None,
                    px_per_10cm_used=px_used or px_per_10cm,
                    calculated_at=datetime.now(UTC),
                    search_strategy=categoria,
                )

        yield SimpleNamespace(add_trial=add_trial, add_result=add_result, tmp_path=tmp_path)
    finally:
        if user_id is not None:
            with get_connection() as conn:
                conn.execute("DELETE FROM users WHERE id=%s", (user_id,))


def _write_labels(path, rows):
    lines = ["trial_id,estrategia_manual,observador,data"]
    lines += [f"{t},{s},Sintetico,2026-11-25" for t, s in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _partition(lab, manual, calibracao, avaliacao):
    return write_partition(
        lab.tmp_path / f"particao-{uuid4().hex}.json",
        Partition(21, 0.3, file_sha256(manual), tuple(calibracao), tuple(avaliacao)),
    )


def _agreement(subconjunto, manual, particao, saida):
    return runner.invoke(
        cli.app,
        [
            "strategy",
            "agreement",
            "--subconjunto",
            subconjunto,
            "--manual",
            str(manual),
            "--particao",
            str(particao),
            "--saida",
            str(saida),
        ],
    )


def _round(saida):
    return json.loads(next(saida.glob("agreement-*/rodada.json")).read_text(encoding="utf-8"))


def test_split_writes_partition_once(lab):
    manual = _write_labels(
        lab.tmp_path / "rotulos.csv",
        [(i, s) for i, s in enumerate(["espacial"] * 4 + ["serial"] * 3 + ["aleatoria"] * 3, 1)],
    )
    particao = lab.tmp_path / "particao.json"
    args = ["strategy", "split", "--manual", str(manual), "--particao", str(particao)]

    first = runner.invoke(cli.app, args)
    assert first.exit_code == 0, first.output
    record = json.loads(particao.read_text(encoding="utf-8"))
    assert len(record["avaliacao"]) == 3  # round(4*0,3)+round(3*0,3)+round(3*0,3) = 1+1+1
    second = runner.invoke(cli.app, args)
    assert second.exit_code == 1
    assert "Já existe" in second.output


def test_pairs_with_latest_classification_and_excludes_invalid_trials(lab):
    ids = [lab.add_trial() for _ in range(7)]
    spatial, serial, random_, later_metric, unclassified, never, stale = ids
    lab.add_result(spatial, "spatial")
    lab.add_result(serial, "serial")
    lab.add_result(random_, "random")
    # Classificado, mas um comando posterior deixou a linha atual com search_strategy nulo.
    lab.add_result(later_metric, "serial")
    lab.add_result(later_metric, None, comando="metrics displacement")
    lab.add_result(unclassified, None)
    lab.add_result(stale, "spatial", px_used=1.0)

    manual = _write_labels(
        lab.tmp_path / "rotulos.csv",
        [
            (spatial, "espacial"),
            (serial, "serial"),
            (random_, "aleatoria"),
            (later_metric, "serial"),
            (unclassified, "aleatoria"),
            (never, "espacial"),
            (stale, "espacial"),
        ],
    )
    particao = _partition(lab, manual, calibracao=ids[4:], avaliacao=ids[:4])
    saida = lab.tmp_path / "rodadas"

    result = _agreement("avaliacao", manual, particao, saida)
    assert result.exit_code == 0, result.output + repr(result.exception)
    record = _round(saida)
    assert record["status"] == "aprovado"
    assert record["n"] == 4
    assert record["kappa"] == pytest.approx(1.0)
    assert {p["trial_id"] for p in record["pares"]} == set(ids[:4])
    assert record["limiares"] == LIMIARES
    assert "não participaram do ajuste" in record["declaracao"]


def test_excluded_reasons_and_rejected_round(lab):
    ids = [lab.add_trial() for _ in range(8)]
    for trial_id, categoria in zip(
        ids[:4], ["spatial", "spatial", "serial", "random"], strict=True
    ):
        lab.add_result(trial_id, categoria)
    lab.add_result(ids[4], None)  # não classificado pela regra
    # ids[5]: nunca passou pelo `strategy classify`
    lab.add_result(ids[6], "spatial", px_used=1.0)  # escala diferente da montagem atual
    lab.add_result(ids[7], "spatial")
    manual = _write_labels(
        lab.tmp_path / "rotulos.csv",
        list(
            zip(
                ids,
                [
                    "espacial",
                    "serial",
                    "aleatoria",
                    "serial",
                    "aleatoria",
                    "serial",
                    "espacial",
                    "espacial",
                ],
                strict=True,
            )
        ),
    )
    particao = _partition(lab, manual, calibracao=ids[:7], avaliacao=[ids[7]])
    saida = lab.tmp_path / "rodadas"

    result = _agreement("calibracao", manual, particao, saida)
    assert result.exit_code == 2, result.output + repr(result.exception)
    record = _round(saida)
    assert record["status"] == "reprovado"
    assert record["n"] == 4
    assert "não é o resultado final" in record["declaracao"]
    motivos = {e["trial_id"]: e["motivo"] for e in record["excluidos"]}
    assert set(motivos) == {ids[4], ids[5], ids[6]}
    assert "não classificado" in motivos[ids[4]]
    assert "sem `strategy classify`" in motivos[ids[5]]
    assert "obsoleta" in motivos[ids[6]]
    assert ids[7] not in motivos  # está na avaliação, não nesta rodada

    result = _agreement("avaliacao", manual, particao, lab.tmp_path / "aval")
    assert result.exit_code == 1  # só 1 trial na avaliação
    assert "ao menos 3" in result.output


def test_partition_citing_unlabeled_trial_is_refused(lab):
    ids = [lab.add_trial() for _ in range(3)]
    manual = _write_labels(
        lab.tmp_path / "rotulos.csv",
        list(zip(ids, ["espacial", "serial", "aleatoria"], strict=True)),
    )
    particao = _partition(lab, manual, calibracao=ids, avaliacao=[10**9])

    result = _agreement("calibracao", manual, particao, lab.tmp_path / "rodadas")
    assert result.exit_code == 1
    assert "sem rótulo manual" in result.output


def test_divergent_thresholds_are_refused(lab):
    ids = [lab.add_trial() for _ in range(3)]
    lab.add_result(ids[0], "spatial")
    lab.add_result(ids[1], "serial")
    lab.add_result(ids[2], "random", limiares=LIMIARES | {"erros_ate_alvo_max": 1})
    manual = _write_labels(
        lab.tmp_path / "rotulos.csv",
        list(zip(ids, ["espacial", "serial", "aleatoria"], strict=True)) + [(10**9, "serial")],
    )
    particao = _partition(lab, manual, calibracao=[10**9], avaliacao=ids)

    result = _agreement("avaliacao", manual, particao, lab.tmp_path / "rodadas")
    assert result.exit_code == 1
    assert "limiares diferentes" in result.output


def test_history_lists_rounds_and_flags_reevaluation(lab):
    ids = [lab.add_trial() for _ in range(3)]
    for trial_id, categoria in zip(ids, ["spatial", "serial", "random"], strict=True):
        lab.add_result(trial_id, categoria)
    manual = _write_labels(
        lab.tmp_path / "rotulos.csv",
        list(zip(ids, ["espacial", "serial", "aleatoria"], strict=True)) + [(10**9, "serial")],
    )
    particao = _partition(lab, manual, calibracao=[10**9], avaliacao=ids)
    saida = lab.tmp_path / "rodadas"
    assert _agreement("avaliacao", manual, particao, saida).exit_code == 0

    # Ajuste depois de ver o kappa da avaliação: reclassifica com outro limiar.
    for trial_id, categoria in zip(ids, ["spatial", "serial", "random"], strict=True):
        lab.add_result(trial_id, categoria, limiares=LIMIARES | {"erros_ate_alvo_max": 2})
    second = _agreement("avaliacao", manual, particao, saida)
    assert second.exit_code == 0
    assert "otimista" in second.output

    history = runner.invoke(cli.app, ["strategy", "agreement-history", "--saida", str(saida)])
    assert history.exit_code == 0
    assert history.output.count("avaliacao") == 2
    assert "aviso:" in history.output
