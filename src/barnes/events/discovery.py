"""Evento de descoberta (D) por buraco: distância e orientação da cabeça (US-11).

Função pura: recebe a trajetória já extraída (`barnes.pose.trajectory`, em cm,
eixos de imagem), a geometria da montagem (em pixels, `barnes.geometry.holes`),
a escala px->cm da montagem e os dois limiares de `configs/default.yaml`, e
devolve o primeiro quadro de cada buraco em que o focinho fica abaixo da
distância limite **e** a cabeça orientada dentro do limiar angular (RN01).
Sem banco, sem vídeo: o recálculo depois de um limiar revisado (RN04) é só
chamar de novo com a mesma trajetória e os novos limiares — a orquestração
(ler o trial, gravar a execução e os eventos) fica na CLI.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import yaml

from barnes.geometry.holes import MazeGeometry
from barnes.geometry.reference_frame import circular_distance_deg

DEFAULT_CONFIG_PATH = Path("configs/default.yaml")


class DiscoveryConfigError(ValueError):
    """Seção `encontrar` ausente ou inválida em `configs/default.yaml` (RN02)."""


@dataclass(frozen=True)
class DiscoveryParams:
    """Os dois limiares de descoberta (seção `encontrar` de `configs/default.yaml`).

    Attributes:
        distance_cm: Distância máxima focinho->buraco, em cm (RN01, C1).
        angle_deg: Desvio angular máximo entre a orientação da cabeça e a
            direção ao buraco, em graus (RN01, C1).
    """

    distance_cm: float
    angle_deg: float


@dataclass(frozen=True)
class DiscoveryEvent:
    """Descoberta de um buraco: primeiro quadro que satisfez os dois limiares (RN01/RN03).

    Attributes:
        hole_number: Índice do buraco na montagem, 0..N-1.
        quadro: Índice do quadro (coluna `quadro` da trajetória).
        t_s: Segundos desde o início do intervalo útil (mesma referência da trajetória).
        distancia_cm: Distância focinho->buraco nesse quadro.
        angulo_deg: Diferença angular entre a cabeça e a direção ao buraco nesse quadro.
    """

    hole_number: int
    quadro: int
    t_s: float
    distancia_cm: float
    angulo_deg: float


def _value(section: Mapping, key: str, where: str) -> Any:
    value = section.get(key) if isinstance(section, Mapping) else None
    if value is None:
        raise DiscoveryConfigError(
            f"'{where}.{key}' está vazio em configs/default.yaml: defina o valor (G3, US-11)."
        )
    return value


def _number(section: Mapping, key: str, where: str) -> float:
    value = _value(section, key, where)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise DiscoveryConfigError(f"'{where}.{key}' deve ser um número em configs/default.yaml.")
    return float(value)


def load_discovery_params(path: str | Path = DEFAULT_CONFIG_PATH) -> DiscoveryParams:
    """Lê e valida a seção `encontrar` do arquivo de configuração (RN02).

    Args:
        path: Caminho do YAML. Padrão: `configs/default.yaml`, relativo ao
            diretório de trabalho (a raiz do repositório).

    Raises:
        DiscoveryConfigError: Arquivo ou seção ausente, valor vazio (`null`)
            ou fora da faixa — a mensagem nomeia a chave. Os valores de
            produção ficam `null` até o laboratório decidir em G3 (C1); este
            erro é esperado até lá, não um defeito.
    """
    path = Path(path)
    if not path.is_file():
        raise DiscoveryConfigError(f"Arquivo de configuração não encontrado: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    section = data.get("encontrar") if isinstance(data, Mapping) else None
    if not isinstance(section, Mapping):
        raise DiscoveryConfigError(f"Seção 'encontrar' ausente em {path}.")

    distance_cm = _number(section, "distancia_cm", "encontrar")
    if distance_cm <= 0:
        raise DiscoveryConfigError("'encontrar.distancia_cm' deve ser maior que zero.")
    angle_deg = _number(section, "angulo_graus", "encontrar")
    if not 0 < angle_deg <= 180:
        raise DiscoveryConfigError("'encontrar.angulo_graus' deve estar entre 0 (exclusive) e 180.")
    return DiscoveryParams(distance_cm=distance_cm, angle_deg=angle_deg)


def detect_discoveries(
    table: pa.Table,
    geometry: MazeGeometry,
    cm_per_px: float,
    params: DiscoveryParams,
) -> list[DiscoveryEvent]:
    """Primeiro quadro de descoberta de cada buraco da montagem (RN01/RN03).

    Um buraco sem nenhum quadro que satisfaça os dois limiares simplesmente
    não aparece na lista (Cenário 2) — ausência de evento, não um evento
    "não encontrado". Reaproximações depois da primeira descoberta são
    ignoradas (RN03): só o primeiro quadro qualificado por buraco é devolvido.

    Args:
        table: Trajetória já validada (`barnes.pose.trajectory.read_trajectory`).
        geometry: Geometria da montagem do trial, em pixels (`barnes.db.maze_configs.get_maze_config`).
        cm_per_px: Escala px->cm da montagem (`barnes.db.calibration`).
        params: Os dois limiares (`load_discovery_params`).

    Returns:
        Um `DiscoveryEvent` por buraco descoberto, na ordem de `geometry.holes`.
    """
    quadro = table.column("quadro").to_numpy()
    t_s = table.column("t_s").to_numpy()
    focinho_x = table.column("focinho_x_cm_image").to_numpy()
    focinho_y = table.column("focinho_y_cm_image").to_numpy()
    theta = table.column("theta_deg_image").to_numpy()
    pose_valida = table.column("pose_valida").to_numpy()

    events = []
    for hole in geometry.holes:
        hole_x_cm = hole.x_px * cm_per_px
        hole_y_cm = hole.y_px * cm_per_px
        dx = hole_x_cm - focinho_x
        dy = hole_y_cm - focinho_y
        distance = np.hypot(dx, dy)
        direction_deg = np.degrees(np.arctan2(dy, dx)) % 360.0
        angle_diff = circular_distance_deg(theta, direction_deg)

        satisfied = pose_valida & (distance < params.distance_cm) & (angle_diff < params.angle_deg)
        indices = np.flatnonzero(satisfied)
        if indices.size == 0:
            continue
        i = indices[0]
        events.append(
            DiscoveryEvent(
                hole_number=hole.hole_number,
                quadro=int(quadro[i]),
                t_s=float(t_s[i]),
                distancia_cm=float(distance[i]),
                angulo_deg=float(angle_diff[i]),
            )
        )
    return events
