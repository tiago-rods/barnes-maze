"""Janela de revisão dos trechos de pose sinalizados (US-10 RN04/RN05).

Como `barnes.io.calibration_ui`, esta janela só coleta o que o operador marca.
Não calcula a série nem a cobertura e não grava nada: devolve as correções e os
trechos revisados para a CLI, que regenera a série e registra tudo numa
execução. O estado da revisão (`ReviewSession`) é separado do laço OpenCV para
poder ser testado sem janela.

A janela abre **direto no primeiro trecho pendente** e só navega pelos trechos
sinalizados, com uma margem de contexto, sem varrer o vídeo inteiro (RN04). Os
quadros são lidos uma vez, em sequência (`barnes.io.video.iter_frames`, sem
seek, por causa dos B-frames), e guardados já reduzidos para a tela.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from barnes.io.calibration_ui import _prepare_preview
from barnes.io.video import iter_frames
from barnes.pose.annotations import KEYPOINTS
from barnes.pose.quality import FlaggedSegment, PointCorrection

Point = tuple[float, float]

# BGR por ponto: focinho, centro do corpo, base da cauda.
_POINT_COLORS = {
    KEYPOINTS[0]: (60, 60, 255),
    KEYPOINTS[1]: (60, 220, 60),
    KEYPOINTS[2]: (255, 160, 40),
}
_KEY_ENTER = (10, 13)
_KEY_BACKSPACE = (8, 127)
_KEY_ESCAPE = 27


class ReviewCancelled(RuntimeError):
    """O operador cancelou a revisão; nenhuma correção foi gravada."""


@dataclass(frozen=True)
class ReviewResult:
    """O que o operador fez na revisão.

    Attributes:
        corrections: Pontos marcados, em pixels do quadro original, um por
            quadro e ponto.
        reviewed_segments: Trechos (início, fim) que o operador confirmou como
            revisados, com ou sem correção.
    """

    corrections: tuple[PointCorrection, ...]
    reviewed_segments: tuple[tuple[int, int], ...]

    @property
    def empty(self) -> bool:
        """True se nada foi marcado nem confirmado."""
        return not self.corrections and not self.reviewed_segments


class ReviewSession:
    """Estado da revisão: trecho e quadro atuais, ponto ativo, marcações.

    Args:
        segments: Trechos a revisar, em ordem de quadro.
        first_frame, last_frame: Quadros extremos da série; a margem de
            contexto nunca passa deles.
        margin: Quadros de contexto antes e depois de cada trecho.
    """

    def __init__(
        self,
        segments: Sequence[FlaggedSegment],
        *,
        first_frame: int,
        last_frame: int,
        margin: int = 0,
    ) -> None:
        if not segments:
            raise ValueError("Não há trechos para revisar.")
        if margin < 0:
            raise ValueError("A margem de contexto não pode ser negativa.")
        self.segments = list(segments)
        self.first_frame = first_frame
        self.last_frame = last_frame
        self.margin = margin
        self._marks: dict[tuple[int, str], Point] = {}
        self._history: list[tuple[tuple[int, str], Point | None]] = []
        self._confirmed: set[int] = set()
        pending = [i for i, segment in enumerate(self.segments) if segment.pending]
        self._go_to(pending[0] if pending else 0)

    # --- navegação ---------------------------------------------------------

    @property
    def segment_index(self) -> int:
        """Posição do trecho atual em `segments`."""
        return self._segment_index

    @property
    def segment(self) -> FlaggedSegment:
        """Trecho atual."""
        return self.segments[self._segment_index]

    @property
    def frame(self) -> int:
        """Quadro exibido."""
        return self._frame

    @property
    def point(self) -> str:
        """Ponto que o próximo clique marca."""
        return self._point

    def view_range(self, segment: FlaggedSegment | None = None) -> tuple[int, int]:
        """Quadros navegáveis de um trecho: o trecho mais a margem, dentro da série."""
        segment = segment or self.segment
        return (
            max(self.first_frame, segment.start_frame - self.margin),
            min(self.last_frame, segment.end_frame + self.margin),
        )

    def frames_to_load(self) -> list[int]:
        """Todos os quadros que a revisão pode exibir, em ordem."""
        wanted: set[int] = set()
        for segment in self.segments:
            start, end = self.view_range(segment)
            wanted.update(range(start, end + 1))
        return sorted(wanted)

    def _go_to(self, index: int) -> None:
        self._segment_index = index
        self._frame = self.segment.start_frame
        self._point = (self.segment.missing_points or KEYPOINTS)[0]

    def next_segment(self) -> None:
        """Vai ao início do próximo trecho (fica no último)."""
        self._go_to(min(self._segment_index + 1, len(self.segments) - 1))

    def previous_segment(self) -> None:
        """Vai ao início do trecho anterior (fica no primeiro)."""
        self._go_to(max(self._segment_index - 1, 0))

    def next_frame(self) -> None:
        """Avança um quadro, sem sair do trecho e da margem."""
        self._frame = min(self._frame + 1, self.view_range()[1])

    def previous_frame(self) -> None:
        """Volta um quadro, sem sair do trecho e da margem."""
        self._frame = max(self._frame - 1, self.view_range()[0])

    def select_point(self, point: str) -> None:
        """Escolhe o ponto que o próximo clique marca."""
        if point not in KEYPOINTS:
            raise ValueError(f"Ponto inválido: {point!r}.")
        self._point = point

    # --- marcação ----------------------------------------------------------

    def mark(self, x_px: float, y_px: float) -> None:
        """Marca o ponto ativo no quadro atual, em pixels do quadro original.

        Depois, o ponto ativo passa para o próximo que falta no trecho, para
        marcar os pontos de um quadro em sequência.
        """
        key = (self._frame, self._point)
        self._history.append((key, self._marks.get(key)))
        self._marks[key] = (float(x_px), float(y_px))
        missing = self.segment.missing_points
        if self._point in missing and len(missing) > 1:
            self._point = missing[(missing.index(self._point) + 1) % len(missing)]

    def undo(self) -> None:
        """Desfaz a última marcação (restaura a anterior do mesmo quadro e ponto)."""
        if not self._history:
            return
        key, previous = self._history.pop()
        if previous is None:
            self._marks.pop(key, None)
        else:
            self._marks[key] = previous
        if key[0] == self._frame:
            self._point = key[1]  # o próximo clique remarca o ponto desfeito

    def marks_at(self, frame: int) -> dict[str, Point]:
        """Marcações feitas num quadro, por ponto."""
        return {point: xy for (f, point), xy in self._marks.items() if f == frame}

    def confirm_segment(self) -> bool:
        """Dá o trecho atual por revisado e vai ao próximo ainda não confirmado.

        Returns:
            True se todos os trechos já foram confirmados.
        """
        self._confirmed.add(self._segment_index)
        remaining = [i for i in range(len(self.segments)) if i not in self._confirmed]
        if not remaining:
            return True
        after = [i for i in remaining if i > self._segment_index]
        self._go_to((after or remaining)[0])
        return False

    def is_confirmed(self, index: int | None = None) -> bool:
        """True se o trecho (padrão: o atual) foi confirmado."""
        return (self._segment_index if index is None else index) in self._confirmed

    def result(self) -> ReviewResult:
        """Correções e trechos confirmados, em ordem de quadro."""
        corrections = tuple(
            PointCorrection(frame, point, x, y)
            for (frame, point), (x, y) in sorted(
                self._marks.items(), key=lambda item: (item[0][0], KEYPOINTS.index(item[0][1]))
            )
        )
        reviewed = tuple(
            (self.segments[i].start_frame, self.segments[i].end_frame)
            for i in sorted(self._confirmed)
        )
        return ReviewResult(corrections, reviewed)


# --- Leitura dos quadros -------------------------------------------------------


@dataclass(frozen=True)
class ReviewFrames:
    """Quadros da revisão já reduzidos para a tela.

    Attributes:
        previews: Prévia BGR por índice de quadro.
        ratio: Razão prévia/original, a mesma nos dois eixos
            (`calibration_ui._prepare_preview`): clique na prévia / ratio = pixel original.
    """

    previews: dict[int, np.ndarray]
    ratio: float


def load_review_frames(video_path: str | Path, frames: Iterable[int]) -> ReviewFrames:
    """Lê, numa passada sequencial, só os quadros pedidos, e guarda as prévias.

    Quadro que o vídeo não tiver (vídeo mais curto que o esperado) simplesmente
    não aparece em `previews`; a janela mostra "indisponível".
    """
    wanted = sorted(set(frames))
    previews: dict[int, np.ndarray] = {}
    ratio = 1.0
    if wanted:
        for index, image in iter_frames(video_path, wanted[0], wanted[-1], set(wanted).__contains__):
            previews[index], ratio = _prepare_preview(image)
    return ReviewFrames(previews, ratio)


# --- Janela --------------------------------------------------------------------


def _text(display: np.ndarray, text: str, row: int) -> None:
    location = (8, 22 + 24 * row)
    for color, thickness in (((0, 0, 0), 3), ((255, 255, 255), 1)):
        cv2.putText(
            display, text, location, cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, thickness, cv2.LINE_AA
        )


def _draw(
    session: ReviewSession,
    frames: ReviewFrames,
    overlay: Mapping[int, Mapping[str, Point]],
) -> np.ndarray:
    preview = frames.previews.get(session.frame)
    if preview is None:
        size = next(iter(frames.previews.values())).shape if frames.previews else (480, 640, 3)
        display = np.zeros(size, dtype=np.uint8)
        _text(display, f"Quadro {session.frame} indisponivel no video", 5)
    else:
        display = preview.copy()
    ratio = frames.ratio

    def to_preview(xy: Point) -> tuple[int, int]:
        return round(xy[0] * ratio), round(xy[1] * ratio)

    # Pontos que a série já tem (detectados ou interpolados): círculo vazado.
    for point, xy in overlay.get(session.frame, {}).items():
        cv2.circle(display, to_preview(xy), 5, _POINT_COLORS[point], 1, cv2.LINE_AA)
    # Marcações do operador: círculo cheio com o número do ponto.
    for point, xy in session.marks_at(session.frame).items():
        center = to_preview(xy)
        cv2.circle(display, center, 4, _POINT_COLORS[point], -1, cv2.LINE_AA)
        cv2.putText(
            display, str(KEYPOINTS.index(point) + 1), (center[0] + 6, center[1] - 6),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, _POINT_COLORS[point], 2, cv2.LINE_AA,
        )

    segment = session.segment
    state = "revisado" if session.is_confirmed() else (
        "pendente" if segment.pending else "ja revisado antes"
    )
    lines = (
        (
            f"Trecho {session.segment_index + 1}/{len(session.segments)} ({state}) | "
            f"quadros {segment.start_frame}-{segment.end_frame} | "
            f"faltam: {', '.join(segment.missing_points) or '-'}"
        ),
        (
            f"Quadro {session.frame} | ponto ativo: {session.point} "
            f"[{KEYPOINTS.index(session.point) + 1}]"
        ),
        "n/p: trecho | a/d: quadro | 1/2/3: ponto | clique: marcar | direito/Backspace: desfazer",
        "Enter: trecho revisado | s: salvar e sair | Esc/X: cancelar sem salvar",
    )
    for row, text in enumerate(lines):
        _text(display, text, row)
    return display


def collect_review(
    frames: ReviewFrames,
    session: ReviewSession,
    *,
    overlay: Mapping[int, Mapping[str, Point]] | None = None,
    window_name: str = "Barnes - revisao de pose",
) -> ReviewResult:
    """Abre a janela de revisão e devolve o que o operador marcou ao salvar.

    Teclas: `n`/`p` próximo/anterior trecho; `d`/`a` próximo/anterior quadro;
    `1`/`2`/`3` escolhem focinho/centro do corpo/base da cauda; clique esquerdo
    marca o ponto ativo; clique direito ou Backspace desfaz; Enter dá o trecho
    por revisado e vai ao próximo; `s` salva e sai. Esc, `x` ou fechar a janela
    cancelam sem salvar.

    Args:
        frames: Quadros de `load_review_frames(session.frames_to_load())`.
        session: Estado inicial (já posicionado no primeiro trecho pendente).
        overlay: Pontos que a série já tem, em pixels, por quadro e ponto.
        window_name: Título da janela.

    Raises:
        ReviewCancelled: Se o operador cancelar.
        RuntimeError: Se não houver ambiente gráfico para abrir a janela.
    """
    overlay = overlay or {}
    created = False
    try:
        cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
        created = True

        def on_mouse(event: int, x: int, y: int, flags: int, param: object) -> None:
            if event == cv2.EVENT_LBUTTONDOWN and session.frame in frames.previews:
                session.mark(x / frames.ratio, y / frames.ratio)
            elif event == cv2.EVENT_RBUTTONDOWN:
                session.undo()

        # No backend win32, registrar o callback antes do primeiro imshow pode
        # não vincular à janela (mesmo ajuste de `collect_segments`).
        cv2.imshow(window_name, _draw(session, frames, overlay))
        cv2.waitKey(1)
        cv2.setMouseCallback(window_name, on_mouse)
        actions = {
            ord("n"): session.next_segment,
            ord("p"): session.previous_segment,
            ord("d"): session.next_frame,
            ord("a"): session.previous_frame,
        }
        for number, point in enumerate(KEYPOINTS, start=1):
            actions[ord(str(number))] = lambda point=point: session.select_point(point)
        while True:
            cv2.imshow(window_name, _draw(session, frames, overlay))
            key = cv2.waitKey(20) & 0xFF
            if key in (_KEY_ESCAPE, ord("x"), ord("X")):
                raise ReviewCancelled("Revisão cancelada; nenhuma correção foi gravada.")
            try:
                visible = cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE)
            except cv2.error:
                visible = 0
            if visible < 1:
                raise ReviewCancelled("Janela fechada; nenhuma correção foi gravada.")
            if key in (ord("s"), ord("S")):
                return session.result()
            if key in _KEY_ENTER:
                session.confirm_segment()
            elif key in _KEY_BACKSPACE:
                session.undo()
            elif key in actions:
                actions[key]()
    except cv2.error as exc:
        raise RuntimeError(
            "Não foi possível abrir ou atualizar a janela de revisão. "
            "Use um ambiente gráfico com opencv-python instalado."
        ) from exc
    finally:
        if created:
            try:
                cv2.destroyWindow(window_name)
            except cv2.error:
                pass  # A janela pode já ter sido fechada pela barra de título.
