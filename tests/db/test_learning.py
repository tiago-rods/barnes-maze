import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from barnes.db.connection import get_connection
from barnes.db.executions import record_processing_execution
from barnes.db.learning import load_learning_rows
from barnes.db.trial_results import insert_trial_result
from barnes.provenance import GitState, ThresholdsSnapshot
from barnes.report.learning import export_learning

pytestmark = pytest.mark.skipif(
    not os.environ.get("BARNES_DATABASE_URL"), reason="Postgres de teste"
)


@pytest.fixture
def dataset():
    conn = get_connection()
    try:
        user = conn.execute(
            "INSERT INTO users(email,name) VALUES(%s,'US22') RETURNING id",
            (f"{uuid4()}@test.local",),
        ).fetchone()[0]
        experiments, trials, executions = [], [], []
        for animal in range(2):
            exp = conn.execute(
                "INSERT INTO experiments(user_id,name) VALUES(%s,'US22') RETURNING id", (user,)
            ).fetchone()[0]
            experiments.append(exp)
            conn.execute(
                "INSERT INTO subjects(experiment_id,name) VALUES(%s,%s)", (exp, f"Animal {animal}")
            )
            maze = conn.execute(
                """INSERT INTO maze_configs(experiment_id,name,arena_diameter_cm,
                hole_count,hole_diameter_cm,px_per_10cm,calibration_date)
                VALUES(%s,'maze',90,20,5,100,CURRENT_DATE) RETURNING id""",
                (exp,),
            ).fetchone()[0]
            for session in (1, 2):
                trial = conn.execute(
                    """INSERT INTO trials(experiment_id,maze_config_id,filename,
                    filepath,phase,day_number,trial_number_in_day,content_hash,width_px,height_px,
                    fps_declared,fps_real,frame_count,duration_s)
                    VALUES(%s,%s,'absent.mp4','data/raw/absent.mp4','acquisition',%s,1,%s,
                           64,64,25,25,250,10) RETURNING id""",
                    (exp, maze, session, str(uuid4())),
                ).fetchone()[0]
                trials.append(trial)
                for version in (1, 2):
                    eid = record_processing_execution(
                        conn,
                        trial_id=trial,
                        maze_config_id=maze,
                        parameters={"comando": "teste US22"},
                        thresholds=ThresholdsSnapshot(
                            values={"test": True}, sha256="b" * 64, path="test"
                        ),
                        git=GitState(commit="a" * 40, dirty=False),
                        video_hash="c" * 64,
                        started_at=datetime.now(UTC),
                        model_id="model-test",
                    )
                    insert_trial_result(
                        conn,
                        trial,
                        execucao_id=eid,
                        distance_cm=20 * version,
                        speed_mean_cm=2,
                        route_efficiency=None,
                        px_per_10cm_used=100,
                        calculated_at=datetime.now(UTC),
                        primary_latency_s=version,
                        primary_errors=version,
                        entropy_bits=0.5 * version,
                        primary_event=(session == 1),
                        total_event=None,
                    )
                    executions.append(eid)
        yield conn, experiments, trials, executions
    finally:
        conn.rollback()
        conn.close()


def test_latest_rows_filters_and_censoring(dataset, tmp_path, monkeypatch):
    conn, experiments, _trials, executions = dataset
    rows = load_learning_rows(conn, experiment_ids=experiments)
    assert len(rows) == 4
    assert {r["execucao_id"] for r in rows} == set(executions[1::2])
    assert {r["entropy"] for r in rows} == {1.0}
    assert sum(r["observed"] is False for r in rows) == 2
    assert all(not r["stale"] for r in rows)
    assert len(load_learning_rows(conn, experiment_ids=experiments[:1])) == 2
    assert load_learning_rows(conn, experiment_ids=experiments, phase="probe") == []
    assert all(
        r["observed"] is None
        for r in load_learning_rows(conn, event="total", experiment_ids=experiments)
    )
    import cv2

    monkeypatch.setattr(cv2, "VideoCapture", lambda *a, **k: pytest.fail("Acesso ao vídeo"))
    output = export_learning(rows, tmp_path / "curves")
    assert (output / "grupo.pdf").is_file()
    assert len(list(output.glob("*.svg"))) == 3


def test_missing_result_and_recalibration(dataset):
    conn, experiments, trials, _ = dataset
    conn.execute("DELETE FROM trial_results WHERE trial_id=%s", (trials[0],))
    rows = load_learning_rows(conn, experiment_ids=experiments)
    missing = next(r for r in rows if r["trial_id"] == trials[0])
    assert missing["observed"] is None and missing["execucao_id"] is None
    conn.execute(
        "UPDATE maze_configs SET px_per_10cm=200 WHERE experiment_id=ANY(%s)", (experiments,)
    )
    assert all(r["stale"] for r in load_learning_rows(conn, experiment_ids=experiments))


@pytest.mark.parametrize("kwargs", [{"phase": "bad"}, {"event": "bad"}, {"experiment_ids": []}])
def test_invalid_filters(dataset, kwargs):
    with pytest.raises(ValueError):
        load_learning_rows(dataset[0], **kwargs)
