"""Detecção auxiliar de geometria a partir de um quadro de referência (US-04).

Puras (nenhuma chamada a `cv2.imshow`/`waitKey`/`setMouseCallback`): servem
de ponto de partida para o ajuste manual, tanto na janela OpenCV de
`barnes maze create` (`cli.py`) quanto no equivalente em canvas do wizard
web — a mesma detecção, duas interfaces diferentes por cima dela.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from barnes.geometry.holes import Hole, MazeGeometry


def detect_platform_circle(frame: np.ndarray) -> tuple[float, float, float] | None:
    """Estima centro e raio da plataforma a partir do quadro (threshold + contorno).

    Assume a plataforma como a maior região clara contígua do quadro — mesma
    técnica padrão de segmentação por limiar usada em `barnes.io.video`/
    tracking de vídeo em geral (Otsu escolhe o limiar automaticamente, sem
    número mágico fixo, já que a exposição varia entre gravações). Serve só
    como ponto de partida: o operador ainda pode corrigir arrastando o mouse.

    Returns:
        `(center_x_px, center_y_px, radius_px)`, ou `None` se nenhum contorno
        for encontrado.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Abertura morfológica: remove pontes finas onde um objeto externo (mão,
    # cabo) toca a borda da plataforma na segmentação. Sem isso, um contato
    # pequeno já distorce o círculo mínimo envolvente — não é um problema de
    # ângulo/rotação de câmera, é a mão do operador entrando no quadro.
    kernel_size = max(3, round(min(frame.shape[:2]) * 0.035) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    opened = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    (x, y), radius = cv2.minEnclosingCircle(largest)
    return float(x), float(y), float(radius)


def fit_circle_to_points(points: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Círculo de mínimos quadrados (método algébrico de Kása) por um conjunto de pontos."""
    xs = np.array([p[0] for p in points], dtype=np.float64)
    ys = np.array([p[1] for p in points], dtype=np.float64)
    design = np.column_stack((2 * xs, 2 * ys, np.ones_like(xs)))
    target = xs**2 + ys**2
    (center_x, center_y, c), *_ = np.linalg.lstsq(design, target, rcond=None)
    radius = math.sqrt(max(c + center_x**2 + center_y**2, 0.0))
    return float(center_x), float(center_y), float(radius)


def detect_hole_candidates(
    frame: np.ndarray, expected_hole_area_fraction: float
) -> list[tuple[float, float]]:
    """Localiza os centros das regiões escuras e aproximadamente circulares da plataforma.

    São os candidatos a buraco: dentro do disco da plataforma (maior contorno
    claro), as regiões escuras cuja área é compatível com o buraco físico
    informado. `expected_hole_area_fraction` — (diâmetro do buraco / diâmetro
    da arena)², já derivável dos dois `--*-diameter-cm` informados na criação
    da montagem — delimita essa área esperada; não é um valor arbitrário.

    Usada tanto por `detect_holes_ring` (ajusta o círculo todo) quanto por
    `snap_holes_to_detected_centers` (corrige buraco a buraco na
    confirmação) — a mesma varredura serve às duas correções.

    Returns:
        Lista de centros `(x_px, y_px)`, possivelmente vazia (sombra, reflexo
        ou o animal cobrindo buracos reduzem a contagem encontrada).
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    platform_contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not platform_contours:
        return []
    platform = max(platform_contours, key=cv2.contourArea)
    platform_area = cv2.contourArea(platform)
    if platform_area <= 0:
        return []

    mask = np.zeros(thresh.shape, dtype=np.uint8)
    cv2.drawContours(mask, [platform], -1, 255, -1)
    dark_inside = cv2.bitwise_and(cv2.bitwise_not(thresh), mask)

    # Abertura morfológica 3x3 — o menor kernel que ainda rompe uma ponte fina
    # de 1-2 px (sombra encostando no buraco, ou o buraco encostando na borda
    # da máscara da plataforma), sem erodir o próprio buraco. Testado contra
    # vídeo real: um kernel maior (5, 7) chega a apagar buracos pequenos por
    # completo em vez de só limpar a ponte — não é um ganho livre de subir o
    # tamanho.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    dark_inside = cv2.morphologyEx(dark_inside, cv2.MORPH_OPEN, kernel)

    # Margem generosa (0.2x a 6x da área esperada): o buraco no vídeo pode
    # parecer menor que o diâmetro físico (sombra parcial) ou maior
    # (penumbra ao redor), mas um ruído de poucos pixels ou o corpo do
    # animal ficam bem fora dessa faixa.
    min_area = 0.2 * expected_hole_area_fraction * platform_area
    max_area = 6.0 * expected_hole_area_fraction * platform_area

    centers: list[tuple[float, float]] = []
    hole_contours, _ = cv2.findContours(dark_inside, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in hole_contours:
        area = cv2.contourArea(contour)
        if not (min_area < area < max_area):
            continue
        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0 or 4 * math.pi * area / perimeter**2 < 0.5:
            continue  # descarta contornos alongados (sombra, pata, cauda)
        moments = cv2.moments(contour)
        if moments["m00"] == 0:
            continue
        centers.append((moments["m10"] / moments["m00"], moments["m01"] / moments["m00"]))
    return centers


def detect_holes_ring(
    frame: np.ndarray, expected_hole_area_fraction: float
) -> tuple[float, float, float] | None:
    """Estima centro e raio da circunferência dos buracos a partir dos próprios buracos.

    `detect_platform_circle` mede a borda física do disco; aqui o alvo é
    outro: `platform_radius_px` é o raio da circunferência *dos buracos*
    (é nela que `generate_holes` distribui os N buracos, RN06), e as duas
    circunferências só coincidem se a câmera for perfeitamente zenital e os
    buracos chegarem até a borda. Em geral não é o caso.

    Ajusta um círculo (mínimos quadrados) aos centros encontrados por
    `detect_hole_candidates`. Precisa de ao menos 3 buracos detectados para
    isso (o mesmo mínimo geométrico de N em `generate_holes`). Serve só como
    ponto de partida: o operador ainda corrige, e `snap_holes_to_detected_centers`
    refina buraco a buraco na confirmação.

    Returns:
        `(center_x_px, center_y_px, radius_px)`, ou `None` se menos de 3
        buracos plausíveis forem encontrados.
    """
    centers = detect_hole_candidates(frame, expected_hole_area_fraction)
    if len(centers) < 3:
        return None
    return fit_circle_to_points(centers)


def snap_holes_to_detected_centers(
    geometry: MazeGeometry, centers: list[tuple[float, float]], max_offset_px: float
) -> tuple[MazeGeometry, int]:
    """Corrige cada buraco para o centro detectado mais próximo, dentro de uma tolerância.

    `detect_holes_ring` só reposiciona o círculo todo (um centro, um raio);
    continua assumindo os N buracos igualmente espaçados nele. Esta função dá
    o passo que faltava: usa os mesmos candidatos (`detect_hole_candidates`)
    para mover cada buraco, individualmente, para cima do buraco real mais
    próximo — o que corrige o desvio que sobra quando a câmera não é
    perfeitamente zenital e um lado da plataforma está mais comprimido que o
    outro. Buracos sem candidato próximo o bastante (sombra, animal, baixo
    contraste) ficam no círculo teórico, como antes.

    Pareamento é guloso e único (menor distância primeiro, cada buraco e cada
    candidato usados no máximo uma vez) para não haver dois buracos puxados
    para o mesmo ponto detectado. `angle_deg` é recalculado a partir da nova
    posição — nunca fica designado a um ponto diferente do que `x_px`/`y_px`
    informam, o que quebraria o referencial de sala (US-05).

    Chamado uma única vez, na confirmação — nunca a cada quadro do ajuste ao
    vivo: um encaixe feito durante o arraste ficaria associado a um
    `hole_number` que deixa de fazer sentido se N ou o centro mudarem depois.

    Args:
        geometry: Geometria confirmada pelo operador (círculo final).
        centers: Candidatos a buraco, de `detect_hole_candidates` sobre o
            mesmo quadro.
        max_offset_px: Distância máxima para considerar um candidato o mesmo
            buraco — maior que isso, o candidato é de outro buraco ou ruído.

    Returns:
        Uma nova `MazeGeometry` com os buracos ajustados, e a contagem de
        buracos efetivamente corrigidos.
    """
    pairs = []
    for hole in geometry.holes:
        for center_index, (cx, cy) in enumerate(centers):
            distance = math.hypot(cx - hole.x_px, cy - hole.y_px)
            if distance <= max_offset_px:
                pairs.append((distance, hole.hole_number, center_index))
    pairs.sort()

    assigned_centers: dict[int, tuple[float, float]] = {}
    used_center_indices: set[int] = set()
    for _distance, hole_number, center_index in pairs:
        if hole_number in assigned_centers or center_index in used_center_indices:
            continue
        assigned_centers[hole_number] = centers[center_index]
        used_center_indices.add(center_index)

    if not assigned_centers:
        return geometry, 0

    snapped_holes = []
    for hole in geometry.holes:
        target = assigned_centers.get(hole.hole_number)
        if target is None:
            snapped_holes.append(hole)
            continue
        new_x, new_y = target
        angle_deg = math.degrees(
            math.atan2(new_y - geometry.center_y_px, new_x - geometry.center_x_px)
        )
        snapped_holes.append(
            Hole(
                hole_number=hole.hole_number,
                angle_deg=angle_deg % 360.0,
                x_px=new_x,
                y_px=new_y,
                radius_px=hole.radius_px,
                is_target=hole.is_target,
            )
        )
    return (
        MazeGeometry(
            center_x_px=geometry.center_x_px,
            center_y_px=geometry.center_y_px,
            platform_radius_px=geometry.platform_radius_px,
            holes=tuple(snapped_holes),
        ),
        len(assigned_centers),
    )
