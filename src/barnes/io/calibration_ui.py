"""Collect reference segments in OpenCV without calculating or saving a scale."""

from __future__ import annotations

from typing import TypeAlias

import cv2
import numpy as np
from numpy.typing import NDArray

Point: TypeAlias = tuple[float, float]
SegmentPoints: TypeAlias = tuple[Point, Point]

_MAX_WIDTH = 1280
_MAX_HEIGHT = 800
_COLORS = ((0, 220, 255), (255, 190, 40), (100, 255, 100))


class CalibrationCancelled(RuntimeError):
    """The researcher cancelled point selection; no calibration was saved."""


def _prepare_preview(frame: NDArray[np.uint8]) -> tuple[NDArray[np.uint8], float]:
    """Returns the resized preview and the single ratio used on both axes.

    Returning the ratio (not just the resized frame) lets the caller scale
    clicked points back with one factor for x and y. Recomputing
    ``original_width / width`` and ``original_height / height`` independently
    from the rounded output dimensions gives each axis a slightly different
    factor (e.g. ~0.06% apart for a 2001x901 frame), which skews calibration
    accuracy right at the margin of the 3% inter-segment check.
    """
    if not isinstance(frame, np.ndarray) or frame.size == 0:
        raise ValueError("O quadro de referência deve ser uma imagem não vazia.")
    if frame.dtype != np.uint8:
        raise ValueError("O quadro de referência deve ter pixels uint8.")
    if frame.ndim == 2:
        preview = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    elif frame.ndim == 3 and frame.shape[2] in (3, 4):
        preview = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR) if frame.shape[2] == 4 else frame.copy()
    else:
        raise ValueError("O quadro de referência deve ser uma imagem cinza, BGR ou BGRA.")
    height, width = preview.shape[:2]
    ratio = min(1.0, _MAX_WIDTH / width, _MAX_HEIGHT / height)
    if ratio < 1.0:
        preview = cv2.resize(
            preview,
            (max(1, round(width * ratio)), max(1, round(height * ratio))),
            interpolation=cv2.INTER_AREA,
        )
    return preview, ratio


def collect_segments(
    frame: NDArray[np.uint8],
    *,
    window_name: str = "Barnes - calibracao",
    segment_count: int = 2,
) -> tuple[SegmentPoints, ...]:
    """Select pairs of endpoints and return their ORIGINAL frame coordinates.

    Left click adds an endpoint. Right click or Backspace undoes the last point;
    R resets the selection. Enter accepts a complete selection. Escape, X or
    closing the window raises :class:`CalibrationCancelled`. This function never
    changes the input image, calculates a scale, or writes to the database.

    A fixed-size OpenCV window prevents a second, uncontrolled resizing of mouse
    coordinates. The image preview fits in 1280 x 800 pixels without upscaling.
    Use ``segment_count=1`` to collect the independent verification distance.
    """
    if isinstance(segment_count, bool) or not isinstance(segment_count, int) or segment_count < 1:
        raise ValueError("A quantidade de segmentos deve ser um inteiro positivo.")

    points: list[Point] = []
    created = False
    try:
        preview, ratio = _prepare_preview(frame)
        height, width = preview.shape[:2]
        scale = 1 / ratio
        required_points = 2 * segment_count

        def on_mouse(event: int, x: int, y: int, flags: int, param: object) -> None:
            if event == cv2.EVENT_RBUTTONDOWN:
                if points:
                    points.pop()
            elif (
                event == cv2.EVENT_LBUTTONDOWN
                and len(points) < required_points
                and 0 <= x < width
                and 0 <= y < height
            ):
                points.append((x * scale, y * scale))

        cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
        created = True
        # No backend win32 do OpenCV, registrar o mouse callback antes do
        # primeiro imshow pode não vincular à superfície da janela (ver
        # mesmo ajuste em cli.py:_adjust_geometry_interactively).
        cv2.imshow(window_name, preview)
        cv2.waitKey(1)
        cv2.setMouseCallback(window_name, on_mouse)
        while True:
            display = preview.copy()
            preview_points = [(round(x / scale), round(y / scale)) for x, y in points]
            for index, point in enumerate(preview_points):
                color = _COLORS[(index // 2) % len(_COLORS)]
                if index % 2:
                    cv2.line(display, preview_points[index - 1], point, color, 2)
                cv2.circle(display, point, 4, color, -1)
                cv2.putText(
                    display,
                    str(index + 1),
                    (point[0] + 7, point[1] - 7),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    color,
                    2,
                    cv2.LINE_AA,
                )
            instructions = (
                f"Pontos: {len(points)}/{required_points} | Clique: marcar | Direito: desfazer",
                "Enter: confirmar | Backspace: desfazer | R: reiniciar | Esc/X: cancelar",
            )
            for index, text in enumerate(instructions):
                location = (8, 22 + 25 * index)
                cv2.putText(
                    display,
                    text,
                    location,
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 0, 0),
                    3,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    display,
                    text,
                    location,
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
            cv2.imshow(window_name, display)
            key = cv2.waitKey(20) & 0xFF
            if key in (27, ord("x"), ord("X")):
                raise CalibrationCancelled("Calibração cancelada; nenhum dado foi salvo.")
            # A window closed through its title bar may make this call fail on
            # some OpenCV backends, or return a non-visible value on others.
            try:
                visible = cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE)
            except cv2.error:
                visible = 0
            if visible < 1:
                raise CalibrationCancelled("Janela fechada; nenhum dado foi salvo.")
            if key in (10, 13) and len(points) == required_points:
                return tuple((points[i], points[i + 1]) for i in range(0, required_points, 2))
            if key in (8, 127) and points:
                points.pop()
            elif key in (ord("r"), ord("R")):
                points.clear()
    except cv2.error as exc:
        raise RuntimeError(
            "Não foi possível abrir ou atualizar a janela de calibração. "
            "Use um ambiente gráfico com opencv-python instalado."
        ) from exc
    finally:
        if created:
            try:
                cv2.destroyWindow(window_name)
            except cv2.error:
                pass  # The window may already have been closed by its title bar.
