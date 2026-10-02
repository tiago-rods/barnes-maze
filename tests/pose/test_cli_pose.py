"""CLI do US-06 (`barnes pose ...`).

Sem Postgres: `sample` e `report` só leem a montagem do banco, então os testes
substituem essa leitura pela geometria sintética (`fake_maze_db`); o resto —
vídeo, intervalo útil, amostragem, exportação e contagem — roda de verdade.
"""

import csv
from pathlib import Path

import pytest
from typer.testing import CliRunner

from barnes import cli
from barnes.pose.annotations import AnnotatedFrame, write_annotations_csv
from barnes.pose.split import read_manifest

REPO_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "default.yaml"
POINTS = ((1.0, 1.0), (2.0, 2.0), (3.0, 3.0))

runner = CliRunner()


def _annotations(tmp_path: Path, frames: list[AnnotatedFrame]) -> Path:
    return write_annotations_csv(frames, tmp_path / "anotacoes.csv")


def test_split_writes_manifest_without_leakage(tmp_path) -> None:
    frames = [AnnotatedFrame(f"t{t}", i * 25, POINTS) for t in range(6) for i in range(3)]
    manifest = tmp_path / "divisao.csv"
    result = runner.invoke(
        cli.app,
        [
            "pose", "split",
            "--annotations", str(_annotations(tmp_path, frames)),
            "--out", str(manifest),
            "--config", str(REPO_CONFIG),
        ],
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert "Verificação de vazamento: OK" in result.output
    assert len(read_manifest(manifest)) == len(frames)

    check = runner.invoke(cli.app, ["pose", "check-split", "--manifest", str(manifest)])
    assert check.exit_code == 0, check.output


def test_split_refuses_incomplete_annotations(tmp_path) -> None:
    incomplete = AnnotatedFrame("t0", 0, ((1.0, 1.0), (float("nan"), float("nan")), (3.0, 3.0)))
    result = runner.invoke(
        cli.app,
        [
            "pose", "split",
            "--annotations", str(_annotations(tmp_path, [incomplete])),
            "--out", str(tmp_path / "divisao.csv"),
            "--config", str(REPO_CONFIG),
        ],
    )  # fmt: skip
    assert result.exit_code == 1
    assert "falta centro_corpo" in result.output
    assert not (tmp_path / "divisao.csv").exists()


def test_check_split_fails_on_leakage(tmp_path) -> None:
    manifest = tmp_path / "divisao.csv"
    manifest.write_text("trial,quadro,conjunto\nt7,0,treino\nt7,25,teste\n", encoding="utf-8")
    result = runner.invoke(cli.app, ["pose", "check-split", "--manifest", str(manifest)])
    assert result.exit_code == 1
    assert "trial t7" in result.output


def test_import_slp_merges_files_from_several_annotators(tmp_path) -> None:
    sio = pytest.importorskip("sleap_io")
    import cv2
    import numpy as np

    skeleton = sio.Skeleton(["focinho", "centro_corpo", "base_cauda"])
    projects = []
    for trial in ("aaa111", "bbb222"):  # um anotador por trial
        frames_dir = tmp_path / trial / "quadros"
        frames_dir.mkdir(parents=True)
        image = frames_dir / "quadro_000010.png"
        cv2.imwrite(str(image), np.zeros((48, 64, 3), dtype=np.uint8))
        instance = sio.Instance.from_numpy(np.array([[1, 2], [3, 4], [5, 6]]), skeleton=skeleton)
        labeled = sio.LabeledFrame(
            video=sio.load_video([str(image)]), frame_idx=0, instances=[instance]
        )
        path = tmp_path / f"{trial}.slp"
        sio.Labels(labeled_frames=[labeled]).save(str(path))
        projects.append(str(path))

    out = tmp_path / "anotacoes.csv"
    result = runner.invoke(cli.app, ["pose", "import-slp", *projects, "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "2 quadros anotados de 2 trial(s)" in result.output


@pytest.fixture
def fake_maze_db(monkeypatch, geometry):
    """Substitui só a leitura da montagem no Postgres pela geometria sintética."""

    class _Connection:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(cli, "get_connection", lambda dsn=None: _Connection())
    monkeypatch.setattr(cli, "get_maze_config", lambda conn, maze_config_id: geometry)


def test_sample_then_report_end_to_end(tmp_path, trial_video, fake_maze_db) -> None:
    out_dir = tmp_path / "annotations"
    result = runner.invoke(
        cli.app,
        [
            "pose", "sample",
            "--video", str(trial_video),
            "--maze-config-id", "1",
            "--start-frame", "0",
            "--scan-step", "1",
            "--out", str(out_dir),
            "--config", str(REPO_CONFIG),
        ],
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert "animal encontrado por contraste" in result.output
    (trial_dir,) = [p for p in out_dir.iterdir() if p.is_dir()]
    assert list((trial_dir / "quadros").glob("quadro_*.png"))

    # Anotação "perfeita": o centro do corpo é a posição estimada na amostragem.
    with (trial_dir / "amostragem.csv").open(encoding="utf-8") as file:
        sampled = list(csv.DictReader(file))
    frames = [
        AnnotatedFrame(
            row["trial"],
            int(row["quadro"]),
            ((0.0, 0.0), (float(row["x_px"]), float(row["y_px"])), (0.0, 0.0)),
        )
        for row in sampled
    ]
    annotations = _annotations(tmp_path, frames)
    report_args = [
        "pose", "report",
        "--annotations", str(annotations),
        "--samples", str(out_dir),
        "--config", str(REPO_CONFIG),
    ]  # fmt: skip

    # Sem --maze-config-id: a montagem vem do amostragem.csv do trial.
    report = runner.invoke(cli.app, report_args)
    assert report.exit_code == 0, report.output
    assert "Montagem(ns) usada(s): 1" in report.output
    assert "Cobertura OK" in report.output

    # Uma montagem diferente da usada na amostragem é recusada, não aplicada em silêncio.
    conflict = runner.invoke(cli.app, [*report_args, "--maze-config-id", "2"])
    assert conflict.exit_code == 1
    assert "contradiz a montagem registrada" in conflict.output
