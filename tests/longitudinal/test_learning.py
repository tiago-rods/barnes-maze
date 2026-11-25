import builtins
import json
from contextlib import contextmanager
from pathlib import Path

import pytest
from typer.testing import CliRunner

from barnes.longitudinal.learning import summarize
from barnes.report.learning import export_learning, make_figure


def row(animal=1, session=1, value=10, **changes):
    return {
        "trial_id": animal * 10 + session,
        "animal_id": animal,
        "animal_name": f"Animal {animal}",
        "session": session,
        "latency": value,
        "errors": value,
        "distance": value,
        "entropy": value,
        "observed": True,
        "stale": False,
        "execucao_id": animal,
        "model_id": "model-1",
        "git_commit": "a" * 40,
        "git_dirty": False,
        "limiares_sha256": "b" * 64,
        "limiares": {"raio": 1},
        "pose_quality": "suficiente",
    } | changes


def test_equal_animal_weight_and_sample_dispersion():
    rows = [
        row(value=0),
        row(value=2),
        row(2, value=9),
        row(3, value=100, observed=False),
        row(4, value=100, observed=None),
        row(5, value=100, stale=True),
    ]
    point = summarize(rows, "latency")["aggregate"][0]
    assert point == {"session": 1, "mean": 5, "sd": pytest.approx(8 / 2**0.5), "n_animals": 2}


def test_single_animal_missing_and_all_censored():
    assert summarize([row(observed=False)], "errors")["aggregate"] == []
    assert summarize([row(entropy=None)], "entropy")["animals"] == []
    assert summarize([row()], "distance")["aggregate"][0]["sd"] is None


def test_figures_identify_censoring_provenance_and_unknown():
    fig = make_figure(
        [row(), row(2, observed=False), row(3, observed=None)],
        title="Teste",
        event="primary",
        aggregate=True,
    )
    texts = "\n".join(t.get_text() for t in fig.texts)
    assert "a" * 40 in texts and "b" * 64 in texts and "model-1" in texts
    assert "censurados=1" in texts and "não avaliados=1" in texts
    assert len(fig.axes) == 4
    for ax in fig.axes:
        assert "Censurado" in " ".join(ax.get_legend_handles_labels()[1])
    fig.clear()


def test_cli_export_without_raw_or_trajectory_access(tmp_path, monkeypatch):
    import barnes.cli_learning as cli
    from barnes.cli import app

    @contextmanager
    def connection(*args):
        yield object()

    monkeypatch.setattr(cli, "get_connection", connection)
    monkeypatch.setattr(cli, "load_learning_rows", lambda *a, **k: [row(), row(2, 2)])
    original = builtins.open
    path_open = Path.open

    def guard(path):
        normalized = str(path).replace("\\", "/")
        assert "data/raw" not in normalized
        assert not normalized.endswith((".mp4", ".parquet", ".slp"))

    def guarded_open(path, *args, **kwargs):
        guard(path)
        return original(path, *args, **kwargs)

    def guarded_path_open(path, *args, **kwargs):
        guard(path)
        return path_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(Path, "open", guarded_path_open)
    import cv2

    monkeypatch.setattr(cv2, "VideoCapture", lambda *a, **k: pytest.fail("Abriu vídeo"))
    result = CliRunner().invoke(app, ["metrics", "learning-curves", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    manifest_path = next(tmp_path.glob("*/manifest.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["figures"]) == 9
    for filename in manifest["figures"]:
        assert (manifest_path.parent / filename).stat().st_size > 100


def test_export_does_not_overwrite_and_empty_is_clear(tmp_path):
    with pytest.raises(FileExistsError):
        export_learning([row()], tmp_path)
    with pytest.raises(ValueError, match="Nenhum trial"):
        export_learning([], tmp_path / "empty")


def test_failed_export_cleans_only_new_directory(tmp_path, monkeypatch):
    from matplotlib.figure import Figure

    monkeypatch.setattr(Figure, "savefig", lambda *a, **k: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        export_learning([row()], tmp_path / "new")
    assert not (tmp_path / "new").exists()
