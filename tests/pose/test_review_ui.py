"""Revisão dos trechos sinalizados (US-10 RN04, SCRUM-131), sem abrir janela.

O laço OpenCV de `collect_review` é fino; a navegação e a marcação vivem em
`ReviewSession`, testada aqui diretamente, e a leitura dos quadros em
`load_review_frames`, testada com um vídeo sintético.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from barnes.pose.annotations import KEYPOINTS
from barnes.pose.quality import FlaggedSegment, PointCorrection
from barnes.pose.review_ui import ReviewResult, ReviewSession, load_review_frames

SNOUT, CENTER, TAIL = KEYPOINTS

SEGMENTS = [
    FlaggedSegment(50, 55, (TAIL,), pending=False),  # revisado numa sessão anterior
    FlaggedSegment(100, 105, (SNOUT, TAIL), pending=True),
    FlaggedSegment(200, 202, (CENTER,), pending=True),
]


def _session(margin=2, segments=SEGMENTS):
    return ReviewSession(segments, first_frame=0, last_frame=203, margin=margin)


def test_opens_directly_at_the_first_pending_segment():
    session = _session()
    assert session.segment_index == 1
    assert session.frame == 100
    assert session.point == SNOUT


def test_jumps_between_segments_and_clamps_frames_to_segment_plus_margin():
    session = _session()
    session.next_segment()
    assert (session.segment_index, session.frame, session.point) == (2, 200, CENTER)
    for _ in range(10):
        session.next_frame()
    assert session.frame == 203  # 202 + margem 2, mas a série acaba em 203
    session.next_segment()
    assert session.segment_index == 2  # fica no último
    session.previous_segment()
    session.previous_segment()
    assert (session.segment_index, session.frame) == (0, 50)
    for _ in range(10):
        session.previous_frame()
    assert session.frame == 48


def test_frames_to_load_are_only_the_segments_plus_margin():
    assert _session(margin=1).frames_to_load() == [
        *range(49, 57), *range(99, 107), *range(199, 204)
    ]


def test_marking_cycles_through_missing_points_and_undo_restores():
    session = _session()
    session.mark(10.0, 20.0)
    assert session.point == TAIL  # próximo ponto que falta no trecho
    session.mark(11.0, 21.0)
    assert session.point == SNOUT
    assert session.marks_at(100) == {SNOUT: (10.0, 20.0), TAIL: (11.0, 21.0)}

    session.mark(12.0, 22.0)  # remarca o focinho
    session.undo()
    assert session.marks_at(100)[SNOUT] == (10.0, 20.0)
    assert session.point == SNOUT
    session.undo()
    session.undo()
    assert session.marks_at(100) == {}
    session.undo()  # nada a desfazer: não quebra


def test_confirming_moves_to_the_next_unconfirmed_segment():
    session = _session()
    assert session.confirm_segment() is False
    assert session.segment_index == 2
    assert session.confirm_segment() is False
    assert session.segment_index == 0  # volta ao único ainda não confirmado
    assert session.confirm_segment() is True


def test_result_lists_corrections_in_frame_order_and_confirmed_segments():
    session = _session()
    session.next_frame()
    session.select_point(TAIL)
    session.mark(5.0, 6.0)
    session.previous_frame()
    session.mark(1.0, 2.0)  # focinho no quadro 100
    session.confirm_segment()

    assert session.result() == ReviewResult(
        corrections=(
            PointCorrection(100, SNOUT, 1.0, 2.0),
            PointCorrection(101, TAIL, 5.0, 6.0),
        ),
        reviewed_segments=((100, 105),),
    )
    assert not session.result().empty


def test_without_pending_segments_starts_at_the_first_one():
    session = _session(segments=SEGMENTS[:1])
    assert (session.segment_index, session.frame) == (0, 50)


def test_invalid_sessions_are_refused():
    with pytest.raises(ValueError, match="trechos"):
        ReviewSession([], first_frame=0, last_frame=10)
    with pytest.raises(ValueError, match="margem"):
        ReviewSession(SEGMENTS, first_frame=0, last_frame=10, margin=-1)
    with pytest.raises(ValueError, match="Ponto"):
        _session().select_point("orelha")


def test_load_review_frames_reads_exactly_the_requested_frames(tmp_path):
    video = tmp_path / "numerado.mp4"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (64, 48))
    for index in range(20):  # quadro i em cinza 12·i: níveis distintos mesmo após o mp4v
        writer.write(np.full((48, 64, 3), 12 * index, dtype=np.uint8))
    writer.release()

    frames = load_review_frames(video, [17, 3, 11, 40])
    assert sorted(frames.previews) == [3, 11, 17]  # 40 não existe no vídeo
    assert frames.ratio == 1.0  # 64 x 48 cabe na tela sem reduzir
    for index, image in frames.previews.items():
        assert float(np.mean(image)) == pytest.approx(12 * index, abs=4)


def test_screen_is_drawn_without_opening_a_window():
    from barnes.pose import review_ui

    session = _session()
    session.mark(30.0, 20.0)
    frames = review_ui.ReviewFrames({100: np.zeros((48, 64, 3), np.uint8)}, ratio=0.5)
    overlay = {100: {CENTER: (40.0, 30.0)}}
    drawn = review_ui._draw(session, frames, overlay)
    assert drawn.shape == (48, 64, 3) and drawn.any()
    assert not frames.previews[100].any()  # desenha numa cópia

    session.next_frame()  # quadro 101 não foi carregado: tela de "indisponível"
    assert review_ui._draw(session, frames, overlay).shape == (48, 64, 3)
