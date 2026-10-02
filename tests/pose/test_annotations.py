import math

import pytest

from barnes.pose.annotations import (
    KEYPOINTS,
    AnnotatedFrame,
    AnnotationError,
    _locate,
    from_slp,
    read_annotations_csv,
    trial_key,
    validate_complete,
    write_annotations_csv,
)

NAN = math.nan


def _frame(trial="abc", index=0, points=((1, 2), (3, 4), (5, 6))):
    return AnnotatedFrame(trial, index, tuple((float(x), float(y)) for x, y in points))


def test_keypoint_order_is_fixed() -> None:
    assert KEYPOINTS == ("focinho", "centro_corpo", "base_cauda")


def test_point_by_name() -> None:
    assert _frame().point("centro_corpo") == (3.0, 4.0)


def test_csv_round_trip(tmp_path) -> None:
    frames = [_frame("b", 10), _frame("a", 5, ((1.5, 2.25), (3, 4), (NAN, NAN)))]
    path = write_annotations_csv(frames, tmp_path / "anotacoes.csv")
    loaded = read_annotations_csv(path)

    assert [(f.trial, f.frame_index) for f in loaded] == [("a", 5), ("b", 10)]
    assert loaded[0].points[0] == (1.5, 2.25)
    assert loaded[0].missing() == ["base_cauda"]
    assert loaded[1] == frames[0]


def test_csv_missing_column_raises(tmp_path) -> None:
    path = tmp_path / "anotacoes.csv"
    path.write_text("trial,quadro,focinho_x\n", encoding="utf-8")
    with pytest.raises(AnnotationError, match="colunas"):
        read_annotations_csv(path)


def test_validate_complete_accepts_full_set() -> None:
    validate_complete([_frame("a", 0), _frame("a", 10), _frame("b", 0)])


def test_validate_complete_points_to_missing_point() -> None:
    incomplete = _frame("a", 7, ((1, 2), (NAN, NAN), (5, 6)))
    with pytest.raises(AnnotationError, match="trial a, quadro 7: falta centro_corpo"):
        validate_complete([_frame("a", 0), incomplete])


def test_validate_complete_rejects_duplicates() -> None:
    with pytest.raises(AnnotationError, match="duplicado"):
        validate_complete([_frame("a", 3), _frame("a", 3)])


def test_validate_complete_rejects_empty() -> None:
    with pytest.raises(AnnotationError, match="vazio"):
        validate_complete([])


def test_trial_key_is_hash_prefix() -> None:
    assert trial_key("0123456789abcdef" * 4) == "0123456789ab"


@pytest.mark.parametrize(
    "image",
    [
        "data/annotations/abc123/quadros/quadro_000042.png",
        r"C:\proj\data\annotations\abc123\quadros\quadro_000042.png",
    ],
)
def test_locate_image_from_sampling_export(image) -> None:
    assert _locate([image], 0, {}) == ("abc123", 42)


def test_locate_rejects_foreign_image() -> None:
    with pytest.raises(AnnotationError, match="padrão"):
        _locate(["fotos/img1.png"], 0, {})


@pytest.mark.parametrize("package", ["data/annotations/projeto.pkg.slp", r"C:\proj\anotacoes.SLP"])
def test_locate_rejects_embedded_images_package(package) -> None:
    # Sem esta recusa, o hash do próprio .slp viraria a chave do trial.
    with pytest.raises(AnnotationError, match="embutidas"):
        _locate(package, 0, {})


def test_locate_video_uses_content_hash(make_mp4) -> None:
    video = make_mp4()
    trial, frame = _locate(str(video), 7, {})
    assert len(trial) == 12
    assert frame == 7


def _save_slp(sio, tmp_path, instances_per_frame, node_names=KEYPOINTS):
    """Monta um projeto SLEAP como o da equipe: PNGs exportados por `pose sample`."""
    import cv2
    import numpy as np

    frames_dir = tmp_path / "abc123" / "quadros"
    frames_dir.mkdir(parents=True)
    image = frames_dir / "quadro_000042.png"
    cv2.imwrite(str(image), np.zeros((48, 64, 3), dtype=np.uint8))

    skeleton = sio.Skeleton(list(node_names))
    video = sio.load_video([str(image)])
    instances = [
        sio.Instance.from_numpy(np.array([[1, 2], [3, 4], [5, 6]]), skeleton=skeleton)
        for _ in range(instances_per_frame)
    ]
    labels = sio.Labels(
        labeled_frames=[sio.LabeledFrame(video=video, frame_idx=0, instances=instances)]
    )
    path = tmp_path / "projeto.slp"
    labels.save(str(path))
    return path


def test_from_slp_reads_user_instances(tmp_path) -> None:
    sio = pytest.importorskip("sleap_io")
    (frame,) = from_slp(_save_slp(sio, tmp_path, instances_per_frame=1))
    assert (frame.trial, frame.frame_index) == ("abc123", 42)
    assert frame.points == ((1.0, 2.0), (3.0, 4.0), (5.0, 6.0))


def test_from_slp_rejects_wrong_skeleton(tmp_path) -> None:
    sio = pytest.importorskip("sleap_io")
    path = _save_slp(sio, tmp_path, 1, node_names=("nariz", "corpo", "cauda"))
    with pytest.raises(AnnotationError, match="Esqueleto"):
        from_slp(path)


def test_from_slp_rejects_two_animals(tmp_path) -> None:
    sio = pytest.importorskip("sleap_io")
    with pytest.raises(AnnotationError, match="animal único"):
        from_slp(_save_slp(sio, tmp_path, instances_per_frame=2))
