"""Catálogo de trials (US-27 RN03/RN04, Cenário 3) contra o Postgres de teste."""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from barnes.db.catalog import Situation, list_catalog
from barnes.db.connection import get_connection
from barnes.db.executions import record_processing_execution
from barnes.db.trial_results import insert_trial_result
from barnes.db.trials import insert_trial
from barnes.io.trim import interval_from_seconds
from barnes.io.video import FileStatus, load_trial_video
from barnes.provenance import GitState, ThresholdsSnapshot

pytestmark = pytest.mark.skipif(
    not os.environ.get("BARNES_DATABASE_URL"),
    reason="Requer BARNES_TEST_DATABASE_URL apontando para um Postgres com o schema aplicado.",
)


@pytest.fixture
def conn():
    connection = get_connection()
    yield connection
    connection.rollback()
    connection.close()


@pytest.fixture
def experiment(conn):
    with conn.cursor() as cur:
        user = cur.execute(
            "INSERT INTO users (email, name) VALUES (%s, 'Op') RETURNING id", (str(uuid4()),)
        ).fetchone()[0]
        experiment = cur.execute(
            "INSERT INTO experiments (user_id, name) VALUES (%s, 'Exp') RETURNING id", (user,)
        ).fetchone()[0]
        cur.execute("INSERT INTO subjects (experiment_id, name) VALUES (%s, 'Rato 3')", (experiment,))
        maze = cur.execute(
            """
            INSERT INTO maze_configs (experiment_id, name, arena_diameter_cm, hole_count,
                                      hole_diameter_cm, px_per_10cm, calibration_date)
            VALUES (%s, 'M', 120, 20, 5, 50, CURRENT_DATE) RETURNING id
            """,
            (experiment,),
        ).fetchone()[0]
    return experiment, maze


@pytest.fixture
def add_trial(conn, experiment, make_mp4):
    experiment_id, maze = experiment
    counter = iter(range(1, 100))

    def _add(*, day=1, interval=True, frames=None):
        number = next(counter)
        # Contagem de quadros diferente por trial → conteúdo (hash) diferente.
        video = make_mp4(f"trial_{number}.mp4", frame_count=frames or 10 + number)
        trial = insert_trial(
            conn,
            experiment_id=experiment_id,
            maze_config_id=maze,
            video=load_trial_video(video),
            phase="acquisition",
            day_number=day,
            trial_number_in_day=number,
            rotation_deg=0.0,
            interval=interval_from_seconds(0.0, 0.5, 10.0, manually_adjusted=True)
            if interval
            else None,
        )
        return trial, video

    return _add


def _metric(conn, trial, maze, *, px_per_10cm=50.0):
    execucao_id = record_processing_execution(
        conn,
        trial_id=trial,
        maze_config_id=maze,
        parameters={},
        thresholds=ThresholdsSnapshot({}, "0" * 64, "t.yaml"),
        git=GitState("a" * 40, False),
        video_hash="h",
        started_at=datetime.now(UTC),
    )
    insert_trial_result(
        conn, trial, execucao_id=execucao_id, distance_cm=1.0, speed_mean_cm=1.0,
        route_efficiency=None, px_per_10cm_used=px_per_10cm, calculated_at=datetime.now(UTC),
    )
    return execucao_id


def _entry(entries, trial):
    return next(e for e in entries if e.trial_id == trial)


def test_catalog_lists_animal_session_and_derived_situation(conn, experiment, add_trial):
    experiment_id, maze = experiment
    sem_recorte, _ = add_trial(interval=False)
    carregado, _ = add_trial()
    inferido, _ = add_trial()
    processado, _ = add_trial(day=2)
    obsoleto, _ = add_trial(day=2)
    conn.execute(
        "INSERT INTO execucao (kind, model_id, maze_config_id, trial_id, status, "
        "duration_seconds, artifact_path, metadata) "
        "VALUES ('inferencia', 'sleap-maze-x', %s, %s, 'concluido', 1, 'p', %s)",
        (maze, inferido, Jsonb({})),
    )
    execucao_id = _metric(conn, processado, maze)
    _metric(conn, obsoleto, maze, px_per_10cm=40.0)  # escala diferente da atual (50)

    entries = list_catalog(conn, experiment_id=experiment_id)

    assert {e.trial_id: e.situacao for e in entries} == {
        sem_recorte: Situation.SEM_RECORTE,
        carregado: Situation.CARREGADO,
        inferido: Situation.POSE_INFERIDA,
        processado: Situation.PROCESSADO,
        obsoleto: Situation.OBSOLETO,
    }
    row = _entry(entries, processado)
    assert (row.animal, row.sessao, row.fase) == ("Rato 3", 2, "acquisition")
    assert row.execucao_id == execucao_id
    assert row.cobertura_pose is None  # preenchida só a partir da US-10
    assert row.arquivo is None  # sem verify, nenhum arquivo é tocado


def test_catalog_shows_pose_coverage(conn, experiment, add_trial):
    experiment_id, maze = experiment
    trial, _ = add_trial()
    execucao_id = _metric(conn, trial, maze)
    conn.execute(
        "UPDATE trials SET cobertura_pose = 0.985, cobertura_execucao_id = %s WHERE id = %s",
        (execucao_id, trial),
    )
    assert _entry(list_catalog(conn, experiment_id=experiment_id), trial).cobertura_pose == 0.985


def test_catalog_flags_moved_and_altered_videos_with_trial_id(
    conn, experiment, add_trial, make_mp4, tmp_path
):
    # Cenário 3: vídeo catalogado movido ou substituído → divergência, com o trial.
    experiment_id, _ = experiment
    intacto, _ = add_trial()
    movido, video_movido = add_trial()
    alterado, video_alterado = add_trial()
    destino = tmp_path / "movidos"
    destino.mkdir()
    shutil.move(video_movido, destino / "outro_nome.mp4")
    shutil.copyfile(make_mp4("substituto.mp4", frame_count=77), video_alterado)

    entries = list_catalog(
        conn, experiment_id=experiment_id, verify="hash", search_dirs=[destino]
    )

    assert _entry(entries, intacto).arquivo.status is FileStatus.OK
    moved = _entry(entries, movido)
    assert moved.arquivo.status is FileStatus.MOVIDO
    assert moved.arquivo.found_at == destino / "outro_nome.mp4"
    assert _entry(entries, alterado).arquivo.status is FileStatus.ALTERADO
    assert {e.trial_id for e in entries if e.diverges} == {movido, alterado}


def test_cheap_check_flags_missing_and_resized_video(conn, experiment, add_trial, make_mp4):
    experiment_id, _ = experiment
    ausente, video_ausente = add_trial()
    redimensionado, video = add_trial()
    video_ausente.unlink()
    shutil.copyfile(make_mp4("grande.mp4", frame_count=90), video)

    entries = list_catalog(conn, experiment_id=experiment_id, verify="size")

    assert _entry(entries, ausente).arquivo.status is FileStatus.AUSENTE
    assert _entry(entries, redimensionado).arquivo.status is FileStatus.ALTERADO
