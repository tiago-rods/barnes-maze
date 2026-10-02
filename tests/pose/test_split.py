import pytest

from barnes.pose.annotations import AnnotatedFrame
from barnes.pose.protocol import SplitProportions
from barnes.pose.split import (
    SETS,
    ManifestRow,
    SplitError,
    SplitLeakageError,
    build_manifest,
    check_no_leakage,
    read_manifest,
    split_by_trial,
    summarize,
    write_manifest,
)

PROPORTIONS = SplitProportions(treino=0.7, validacao=0.15, teste=0.15)
POINTS = ((1.0, 1.0), (2.0, 2.0), (3.0, 3.0))


def _frames(trials: int, per_trial: int = 4) -> list[AnnotatedFrame]:
    return [
        AnnotatedFrame(f"t{t:02d}", i * 25, POINTS) for t in range(trials) for i in range(per_trial)
    ]


def test_each_trial_in_exactly_one_set() -> None:
    frames = _frames(20)
    rows = build_manifest(frames, split_by_trial((f.trial for f in frames), PROPORTIONS, 0))
    check_no_leakage(rows)
    assert len(rows) == len(frames)


def test_proportions_are_of_trials() -> None:
    assignment = split_by_trial([f"t{i}" for i in range(20)], PROPORTIONS, 0)
    counts = {name: list(assignment.values()).count(name) for name in SETS}
    assert counts == {"treino": 14, "validacao": 3, "teste": 3}


def test_three_trials_one_per_set() -> None:
    # Os 3 trials representativos de G1: um em cada conjunto.
    assignment = split_by_trial(["a", "b", "c"], PROPORTIONS, 0)
    assert sorted(assignment.values()) == sorted(SETS)


def test_too_few_trials_raises() -> None:
    with pytest.raises(SplitError, match="ao menos 3 trials"):
        split_by_trial(["a", "b"], PROPORTIONS, 0)


def test_invalid_proportions_raise() -> None:
    with pytest.raises(SplitError, match="somar 1"):
        split_by_trial(["a", "b", "c"], SplitProportions(0.5, 0.5, 0.5), 0)


def test_zero_proportion_set_stays_empty() -> None:
    assignment = split_by_trial(["a", "b", "c", "d"], SplitProportions(0.75, 0.0, 0.25), 0)
    assert "validacao" not in assignment.values()


def test_split_is_reproducible_and_seed_dependent() -> None:
    trials = [f"t{i}" for i in range(20)]
    assert split_by_trial(trials, PROPORTIONS, 7) == split_by_trial(trials, PROPORTIONS, 7)
    assert split_by_trial(trials, PROPORTIONS, 7) != split_by_trial(trials, PROPORTIONS, 8)


def test_leakage_detected_and_points_to_trial() -> None:
    # Cenário 3: o mesmo trial com quadros em treino e em teste.
    rows = [
        ManifestRow("t01", 0, "treino"),
        ManifestRow("t01", 50, "teste"),
        ManifestRow("t02", 0, "validacao"),
    ]
    with pytest.raises(SplitLeakageError, match="trial t01 em teste, treino") as info:
        check_no_leakage(rows)
    assert info.value.leaks == {"t01": {"treino", "teste"}}


def test_manifest_round_trip(tmp_path) -> None:
    frames = _frames(5)
    rows = build_manifest(frames, split_by_trial((f.trial for f in frames), PROPORTIONS, 0))
    path = write_manifest(rows, tmp_path / "divisao.csv")
    assert read_manifest(path) == rows


def test_manually_edited_manifest_with_leak_fails(tmp_path) -> None:
    path = tmp_path / "divisao.csv"
    path.write_text("trial,quadro,conjunto\na,0,treino\na,25,teste\n", encoding="utf-8")
    with pytest.raises(SplitLeakageError):
        check_no_leakage(read_manifest(path))


def test_manifest_rejects_unknown_set(tmp_path) -> None:
    path = tmp_path / "divisao.csv"
    path.write_text("trial,quadro,conjunto\na,0,producao\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Conjunto inválido"):
        read_manifest(path)


def test_summarize_counts_trials_and_frames() -> None:
    rows = [
        ManifestRow("a", 0, "treino"),
        ManifestRow("a", 25, "treino"),
        ManifestRow("b", 0, "teste"),
    ]
    assert summarize(rows) == {"treino": (1, 2), "validacao": (0, 0), "teste": (1, 1)}
