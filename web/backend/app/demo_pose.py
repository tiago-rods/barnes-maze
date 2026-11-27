"""Modo DEMONSTRAÇÃO: pose sintética para apresentar o pipeline sem modelo treinado.

**Não é pose real, nem entrega de card.** Não há modelo SLEAP treinado nesta
máquina (nem anotação do laboratório para treiná-lo), então a inferência
real (US-07/08) não roda. Para mostrar o resto do pipeline de ponta a ponta
— série (US-09/10), eventos (US-11..15), métricas (US-16..19), estratégia
(US-20) e curvas (US-22) —, este módulo injeta um backend sintético no
`barnes.pose.inference.infer_trial` real (o parâmetro `backend_factory`, o
mesmo usado pelos testes). Tudo depois disso é o código de produção.

A identidade da demonstração é preservada em todo lugar: `model_id`
`DEMO-SINTETICO-m<montagem>` vai para `execucao.model_id`, para a
proveniência e para o manifesto das curvas; o frontend mostra a faixa DEMO
sempre que o resultado vem desse modelo.

A trajetória: o animal sai do centro, checa três buracos adjacentes ao alvo
(focinho no buraco, cabeça apontada para ele, ~0,6 s cada) e entra no alvo,
onde fica até o fim — um padrão que a regra da US-20 deve chamar de serial.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from barnes.geometry.holes import MazeGeometry
from barnes.pose.annotations import KEYPOINTS
from barnes.pose.dataset import file_sha256, write_json

DEMO_MODEL_PREFIX = "DEMO-SINTETICO"
DEMO_DATASET_ID = "demo-sintetico"
DEMO_NOTICE = "DEMO SINTETICO: nao e um modelo treinado; pose gerada por regra fixa.\n"
DEMO_MODELS_ROOT = Path("models")

NOSE_OFFSET_CM = 2.0
CONFIDENCE = 0.95
JITTER_PX = 0.4
SEED = 20261127

# Roteiro (segundos): ida do centro ao 1º buraco, deslocamento entre buracos, permanência.
TO_FIRST_HOLE_S = 2.5
BETWEEN_HOLES_S = 1.2
CHECK_S = 0.6
SEARCH_HOLES = 3


def is_demo_model(model_id: str | None) -> bool:
    """True se o `model_id` é do modo demonstração."""
    return bool(model_id) and model_id.startswith(DEMO_MODEL_PREFIX)


def demo_model_id(maze_config_id: int) -> str:
    return f"{DEMO_MODEL_PREFIX}-m{maze_config_id}"


def ensure_demo_model(maze_config_id: int, root: Path = DEMO_MODELS_ROOT) -> Path:
    """Cria (uma vez) o diretório do "modelo" demo no formato de `load_model_manifest`.

    Os artefatos são arquivos de texto com o aviso DEMO — não há pesos. O
    manifesto só existe para que a inferência real aceite o diretório e
    registre a identidade da demonstração na proveniência.
    """
    model_id = demo_model_id(maze_config_id)
    model_dir = (root / model_id).resolve()
    if (model_dir / "manifest.json").is_file():
        return model_dir
    (model_dir / "sleap").mkdir(parents=True, exist_ok=True)
    for relative in ("sleap/best.ckpt", "sleap/training_config.yaml", "config.yaml"):
        (model_dir / relative).write_text(DEMO_NOTICE, encoding="utf-8")
    write_json(
        model_dir / "dataset_manifest.json",
        {
            "dataset_id": DEMO_DATASET_ID,
            "maze_config_id": maze_config_id,
            "keypoints": list(KEYPOINTS),
            "aviso": DEMO_NOTICE.strip(),
        },
    )
    write_json(
        model_dir / "manifest.json",
        {
            "schema_version": 1,
            "status": "completed",
            "model_id": model_id,
            "maze_config_id": maze_config_id,
            "dataset_id": DEMO_DATASET_ID,
            "keypoints": list(KEYPOINTS),
            "checkpoint": "sleap/best.ckpt",
            "config_path": "config.yaml",
            "aviso": DEMO_NOTICE.strip(),
            "artifacts": {
                path.relative_to(model_dir).as_posix(): file_sha256(path)
                for path in sorted(model_dir.rglob("*"))
                if path.is_file() and path.name != "manifest.json"
            },
        },
    )
    return model_dir


def _search_holes(geometry: MazeGeometry) -> list[int]:
    """Três buracos adjacentes ao alvo, percorridos no mesmo sentido, terminando no alvo."""
    n = geometry.hole_count
    target = geometry.target_hole.hole_number
    return [(target - k) % n for k in range(SEARCH_HOLES, 0, -1)] + [target]


def synthetic_pose(
    geometry: MazeGeometry, cm_per_px: float, fps: float, n_frames: int
) -> tuple[np.ndarray, np.ndarray]:
    """Gera a pose (pixels de imagem) de `n_frames` quadros desde o início do intervalo útil.

    Returns:
        `points[n_frames, 3, 2]` na ordem `KEYPOINTS` (focinho, centro_corpo,
        base_cauda) e `scores[n_frames, 3]`.
    """
    holes = {hole.hole_number: hole for hole in geometry.holes}
    center = np.array([geometry.center_x_px, geometry.center_y_px])
    # O focinho fica a ~2 cm do centro do corpo, mas nunca a mais de 20% do
    # espaçamento entre buracos — senão, numa montagem com buracos próximos
    # (em pixels), o focinho "alcançaria" o buraco vizinho.
    spacing_px = 2 * math.pi * geometry.platform_radius_px / geometry.hole_count
    nose_px = min(NOSE_OFFSET_CM / cm_per_px, 0.2 * spacing_px)

    # Roteiro em quadros-chave (tempo, posição do corpo) e, por trecho, a
    # orientação da cabeça: `None` = direção do movimento; ângulo = fixa.
    # Para cada buraco: chega a um ponto recuado (radialmente para dentro),
    # avança em linha reta até o focinho ficar sobre o buraco (a cabeça já
    # aponta para ele: D antes de E), permanece, recua e segue.
    times_kf: list[float] = [0.0]
    positions: list[np.ndarray] = [center]
    headings: list[float | None] = []

    def go(duration: float, position: np.ndarray, heading_deg: float | None) -> None:
        times_kf.append(times_kf[-1] + duration)
        positions.append(position)
        headings.append(heading_deg)

    for index, number in enumerate(_search_holes(geometry)):
        hole = holes[number]
        target_xy = np.array([hole.x_px, hole.y_px])
        radial = target_xy - center
        radial /= np.linalg.norm(radial)
        radial_deg = math.degrees(math.atan2(radial[1], radial[0]))
        approach_px = max(1.5 * hole.radius_px, 0.15 * spacing_px)
        at_hole = target_xy - nose_px * radial
        before = at_hole - approach_px * radial
        go(TO_FIRST_HOLE_S if index == 0 else BETWEEN_HOLES_S, before, None)
        go(0.2, before, radial_deg)  # gira a cabeça para o buraco
        go(0.4, at_hole, radial_deg)  # avança: D e depois E
        go(CHECK_S if not hole.is_target else 1e9, at_hole, radial_deg)
        if not hole.is_target:
            go(0.3, before, radial_deg)  # recua de costas, cabeça ainda no buraco

    times = np.arange(n_frames) / fps
    body = np.empty((n_frames, 2))
    heading = np.empty(n_frames)
    last_heading = 0.0
    for i, now in enumerate(times):
        k = int(np.searchsorted(times_kf, now, side="right")) - 1
        k = min(max(k, 0), len(headings) - 1)
        t0, t1 = times_kf[k], times_kf[k + 1]
        p0, p1 = positions[k], positions[k + 1]
        alpha = min(max((now - t0) / (t1 - t0), 0.0), 1.0)
        body[i] = p0 + alpha * (p1 - p0)
        if headings[k] is not None:
            last_heading = headings[k]
        elif np.linalg.norm(p1 - p0) > 1e-9:
            direction = p1 - p0
            last_heading = math.degrees(math.atan2(direction[1], direction[0]))
        heading[i] = last_heading

    rng = np.random.default_rng(SEED)
    body = body + rng.normal(0.0, JITTER_PX, body.shape)
    theta = np.radians(heading)
    offset = np.stack([np.cos(theta), np.sin(theta)], axis=1) * nose_px
    points = np.stack([body + offset, body, body - offset], axis=1)
    scores = np.full((n_frames, 3), CONFIDENCE)
    return points, scores


def synthetic_backend_factory(geometry: MazeGeometry, cm_per_px: float, fps: float):
    """Backend para `infer_trial(backend_factory=...)`: ignora os pixels, segue o roteiro.

    `infer_trial` entrega os quadros do intervalo útil em ordem e em lotes;
    o backend só conta quantos já respondeu para saber o tempo de cada quadro.
    """

    class SyntheticDemoBackend:
        def __init__(self, model_dir, *, device, batch_size):
            self._served = 0
            self._cache: tuple[np.ndarray, np.ndarray] | None = None

        def predict(self, images):
            count = len(images)
            needed = self._served + count
            if self._cache is None or len(self._cache[0]) < needed:
                self._cache = synthetic_pose(geometry, cm_per_px, fps, max(needed, 1024))
            points, scores = self._cache
            start = self._served
            self._served = needed
            return points[start:needed], scores[start:needed]

    return SyntheticDemoBackend
