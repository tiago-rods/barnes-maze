"""Referencial da plataforma e referencial da sala (US-05).

Três referenciais angulares convivem no sistema, todos com a convenção de
`barnes.geometry.holes` (0° apontando para +x, crescente no sentido horário
na tela):

- **Imagem** (`ReferenceFrame.IMAGE`): `Hole.angle_deg`, ângulo do buraco no
  quadro do vídeo. Depende da posição da câmera — muda se ela for deslocada.
- **Plataforma** (`ReferenceFrame.PLATFORM`): `Hole.hole_number`, 0..N-1. Por
  convenção, o buraco 0 de toda montagem é o **buraco físico de referência**
  combinado com o laboratório (a câmera só vê a plataforma de cima, sem marco
  de parede; como a plataforma não gira — B4 —, os buracos são fixos na sala).
- **Sala** (`ReferenceFrame.ROOM`): ângulo fixo na sala, com 0° na posição do
  buraco de referência com a plataforma em repouso::

      sala(k) = (angulo_imagem(k) - angulo_imagem(0) + rotacao) mod 360

  `rotacao` é a rotação da plataforma no trial (`trials.rotation_deg`),
  positiva no mesmo sentido da numeração dos buracos. Como o ângulo de sala
  é relativo ao buraco 0, uma câmera girada ou deslocada (nova montagem, com
  o buraco 0 no mesmo buraco físico) produz os mesmos ângulos de sala.

O buraco-alvo (`Hole.is_target`) é marcado com a plataforma em repouso
(rotação 0): sua posição na sala é fixa, e o índice do buraco que a ocupa
num trial rotacionado é dado por `target_hole_for_trial`.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from barnes.geometry.holes import Hole, MazeGeometry

# Abaixo disto, um ângulo é tratado como 360 ≡ 0 — evita 359.99999999 vindo
# de erro de ponto flutuante na subtração de ângulos.
_ANGLE_EPSILON_DEG = 1e-9


class MissingRotationError(ValueError):
    """Trial(s) sem rotação registrada pedidos numa análise longitudinal (Cenário 3).

    Attributes:
        trial_ids: Ids de **todos** os trials sem rotação, em ordem crescente.
    """

    def __init__(self, trial_ids: list[int]) -> None:
        self.trial_ids = trial_ids
        ids = ", ".join(f"#{trial_id}" for trial_id in trial_ids)
        super().__init__(
            f"Rotação da plataforma não registrada para o(s) trial(s) {ids}. "
            "A análise longitudinal exige a rotação de cada trial e não assume 0° "
            "(US-05 RN01) — registre com `barnes trial set-rotation`."
        )


def require_rotations(rotations: Mapping[int, float | None]) -> dict[int, float]:
    """Garante que todos os trials de uma análise longitudinal têm rotação (RN01/RN03).

    Ponto de entrada obrigatório de toda análise que compara trials no
    referencial da sala (sequência de visitação entre trials, DTW/Fréchet da
    US-24, probe e palpites da US-26): recusa a análise inteira em vez de
    descartar ou zerar em silêncio os trials sem rotação.

    Args:
        rotations: Rotação de cada trial, por id; `None` = não registrada
            (`trials.rotation_deg` NULL).

    Returns:
        As mesmas rotações, com o tipo estreitado para `float`.

    Raises:
        MissingRotationError: Se algum trial não tiver rotação — a mensagem
            lista todos os faltantes, não só o primeiro.
    """
    missing = sorted(trial_id for trial_id, rotation in rotations.items() if rotation is None)
    if missing:
        raise MissingRotationError(missing)
    return {trial_id: float(rotation) for trial_id, rotation in rotations.items()}


class ReferenceFrame(StrEnum):
    """Referencial em que um valor está expresso (US-05 RN05).

    O valor do enum é o sufixo usado nos nomes de coluna das saídas, para que
    cada coluna identifique explicitamente seu referencial
    (ex.: `target_hole_platform`, `target_angle_deg_room`).
    """

    IMAGE = "image"
    PLATFORM = "platform"
    ROOM = "room"

    def column(self, name: str) -> str:
        """Nome de coluna com o sufixo deste referencial (ex.: `angle_deg_room`)."""
        return f"{name}_{self.value}"


def hole_to_room_angle(geometry: MazeGeometry, hole_number: int, *, rotation_deg: float) -> float:
    """Converte índice de buraco (plataforma) em ângulo na sala (RN02).

    Args:
        geometry: Montagem do labirinto, com o buraco 0 no buraco físico de
            referência.
        hole_number: Índice do buraco, 0..N-1.
        rotation_deg: Rotação da plataforma no trial, em graus.

    Returns:
        Ângulo na sala, em graus, normalizado para 0 <= x < 360.

    Raises:
        ValueError: Se `hole_number` estiver fora de 0..N-1.
    """
    hole = _hole(geometry, hole_number)
    reference_deg = geometry.holes[0].angle_deg
    return _normalize(hole.angle_deg - reference_deg + rotation_deg)


def room_angle_to_hole(
    geometry: MazeGeometry, room_angle_deg: float, *, rotation_deg: float
) -> int:
    """Converte ângulo na sala no índice do buraco que o ocupa (RN02).

    Inversa de `hole_to_room_angle`: escolhe o buraco de menor distância
    angular circular, então ângulos entre dois buracos caem no mais próximo.

    Args:
        geometry: Montagem do labirinto.
        room_angle_deg: Ângulo na sala, em graus (qualquer valor; é normalizado).
        rotation_deg: Rotação da plataforma no trial, em graus.

    Returns:
        O índice (0..N-1) do buraco nessa posição da sala.
    """
    image_angle_deg = room_angle_deg - rotation_deg + geometry.holes[0].angle_deg
    nearest = min(
        geometry.holes, key=lambda hole: _circular_distance(hole.angle_deg, image_angle_deg)
    )
    return nearest.hole_number


def target_room_angle(geometry: MazeGeometry) -> float:
    """Ângulo na sala do buraco-alvo, fixo para todos os trials da montagem.

    O alvo é marcado com a plataforma em repouso, então a posição na sala é
    calculada com rotação 0.
    """
    return hole_to_room_angle(geometry, geometry.target_hole.hole_number, rotation_deg=0.0)


def target_hole_for_trial(geometry: MazeGeometry, *, rotation_deg: float) -> int:
    """Índice do buraco que ocupa a posição do alvo num trial com dada rotação (Cenário 1).

    Com rotação 0 (B4: o LNBio não rotaciona), é o próprio buraco marcado
    como alvo na montagem.
    """
    return room_angle_to_hole(geometry, target_room_angle(geometry), rotation_deg=rotation_deg)


def _hole(geometry: MazeGeometry, hole_number: int) -> Hole:
    if not (0 <= hole_number < geometry.hole_count):
        raise ValueError(
            f"Índice de buraco deve estar entre 0 e {geometry.hole_count - 1} "
            f"(recebido {hole_number})."
        )
    return geometry.holes[hole_number]


def _normalize(angle_deg: float) -> float:
    angle_deg %= 360.0
    return 0.0 if 360.0 - angle_deg < _ANGLE_EPSILON_DEG else angle_deg


def _circular_distance(a_deg: float, b_deg: float) -> float:
    diff = abs(a_deg - b_deg) % 360.0
    return min(diff, 360.0 - diff)
