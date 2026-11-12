"""Distância total e velocidade média de um trial (US-18).

Função pura, sem banco e sem vídeo: recebe a trajetória do trial
(`barnes.pose.trajectory`, contrato em `docs/contrato-trajetoria.md`), que já está em
cm (US-09 → RN01) e já cobre só o intervalo útil (US-03). Devolve **uma** distância e
**uma** velocidade média por trial (RN02); não há segmentação por fase (S→D, D→E,
S→E): as distâncias por fase são da US-16/US-13 e as velocidades por fase são
derivadas pelo próprio `barnes_maze.py` do laboratório (RN03/RN04).

Convenções, as mesmas da distância percorrida da US-16 (`metrics.latency`):

- **Ponto**: `centro_corpo` por padrão. Qual ponto o laboratório usa ainda está a
  confirmar (`docs/definicoes-metricas.md`).
- **Distância**: soma dos segmentos entre amostras válidas consecutivas do ponto. Uma
  lacuna de pose que a US-10 não interpolou é atravessada em linha reta entre o último
  ponto antes e o primeiro depois dela — subestima um pouco, nunca inventa trajeto.
- **Duração da velocidade**: do primeiro ao último ponto válido (decisão da equipe na
  SCRUM-220). Dividir pelo intervalo inteiro subestimaria a velocidade sempre que a
  pose falta numa borda; a duração do intervalo e o tempo sem pose nas bordas saem
  junto, para auditoria.
- **Trechos interpolados** (US-10) entram no cálculo, e a fração interpolada sai junto
  (RN05). `interpolado` é marcado **por linha** — basta um dos três pontos ter sido
  preenchido —, então a fração é conservadora: pode ficar um pouco acima da fração do
  ponto usado sozinho.
- **fps variável** (US-01, RN07): a distância não depende do tempo e sai normalmente; a
  velocidade herda a base temporal aproximada e sai com ressalva.
- **Ausência nunca vira zero**: sem amostra válida, distância e velocidade são `None`;
  com uma amostra só, a distância é 0 e a velocidade é `None` (não há duração).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pyarrow as pa

from barnes.metrics.latency import (
    DEFAULT_DISTANCE_POINT,
    TRAJECTORY_POINTS,
    travelled_distance_cm,
)

SPEED_FPS_CAVEAT = (
    "Base temporal aproximada: o vídeo tem fps variável (US-01), então a velocidade "
    "média é aproximada. A distância não depende do tempo e não é afetada (US-18 RN07)."
)

# Colunas complementares do `trials.csv` (US-25 RN04): o esquema do laboratório não tem
# velocidade nem distância do intervalo inteiro (`total_distance` lá é S→E).
EXPORT_COLUMNS = ("path_distance", "mean_speed", "interpolated_fraction", "speed_time_base_approx")


@dataclass(frozen=True)
class Displacement:
    """Distância e velocidade média do trial, com o que é preciso para auditá-las.

    Attributes:
        distance_cm: Distância percorrida pelo ponto, em cm; `None` sem amostra válida.
        mean_speed_cm_s: `distance_cm / duration_s`, em cm/s; `None` com menos de duas
            amostras válidas.
        duration_s: Tempo do primeiro ao último ponto válido; `None` sem amostra válida.
        interval_duration_s: Duração da série (intervalo útil), do primeiro ao último
            quadro.
        edge_gap_s: Tempo do intervalo sem o ponto nas bordas (início + fim), fora de
            `duration_s`; `None` sem amostra válida.
        interpolated_fraction: Fração das amostras usadas que vêm de linhas
            `interpolado` (US-10); `None` sem amostra válida.
        frames_used: Amostras válidas do ponto que entraram na distância.
        frames_total: Quadros da série.
        ponto: Ponto do corpo usado.
        fps_variavel: O vídeo tem fps variável (US-01).
        speed_caveat: Ressalva da velocidade com fps variável (RN07), ou `None`.
        avisos: Demais ressalvas legíveis (pose ausente, amostra única, lacunas).
    """

    distance_cm: float | None
    mean_speed_cm_s: float | None
    duration_s: float | None
    interval_duration_s: float
    edge_gap_s: float | None
    interpolated_fraction: float | None
    frames_used: int
    frames_total: int
    ponto: str
    fps_variavel: bool
    speed_caveat: str | None
    avisos: tuple[str, ...]

    def as_export_columns(self) -> dict[str, float | bool | None]:
        """As colunas complementares do `trials.csv` (US-25 RN04, SCRUM-224).

        Nomes no estilo do laboratório (inglês, sem unidade no nome): distância em cm,
        velocidade em cm/s, fração em [0, 1]. `speed_time_base_approx` é a marca da
        ressalva de fps variável na velocidade.
        """
        return {
            "path_distance": self.distance_cm,
            "mean_speed": self.mean_speed_cm_s,
            "interpolated_fraction": self.interpolated_fraction,
            "speed_time_base_approx": self.fps_variavel,
        }


def compute_displacement(
    trajectory: pa.Table, *, ponto: str = DEFAULT_DISTANCE_POINT
) -> Displacement:
    """Distância total (cm) e velocidade média (cm/s) do trial (RN01, RN02, RN05, RN07).

    Args:
        trajectory: Trajetória do trial (`read_trajectory`): usa `t_s`,
            `<ponto>_x_cm_image`, `<ponto>_y_cm_image`, `<ponto>_valido`,
            `interpolado` e `fps_variavel`.
        ponto: Ponto do corpo usado na distância.

    Returns:
        Uma distância e uma velocidade por trial, com fração interpolada, durações e
        avisos.

    Raises:
        ValueError: Ponto desconhecido, trajetória vazia ou sem as colunas necessárias.
    """
    if ponto not in TRAJECTORY_POINTS:
        raise ValueError(f"Ponto '{ponto}' desconhecido; use um de {', '.join(TRAJECTORY_POINTS)}.")
    columns = (
        "t_s",
        f"{ponto}_x_cm_image",
        f"{ponto}_y_cm_image",
        f"{ponto}_valido",
        "interpolado",
        "fps_variavel",
    )
    missing = [name for name in columns if name not in trajectory.column_names]
    if missing:
        raise ValueError(f"Trajetória sem as colunas: {', '.join(missing)}.")
    if trajectory.num_rows == 0:
        raise ValueError("Trajetória vazia: não há intervalo útil para medir.")
    t_s, x_cm, y_cm, valid, interpolated, fps = (
        trajectory.column(name).to_numpy() for name in columns
    )
    valid = valid.astype(bool)
    interpolated = interpolated.astype(bool)
    fps_variavel = bool(fps.any())
    interval_duration = float(t_s[-1] - t_s[0])
    total = int(t_s.size)
    used = int(valid.sum())

    avisos: list[str] = []
    speed_caveat = SPEED_FPS_CAVEAT if fps_variavel else None

    if used == 0:
        avisos.append(
            f"Nenhuma amostra válida de {ponto} no intervalo útil: distância e velocidade "
            "não calculadas (ausência não é zero)."
        )
        return Displacement(
            distance_cm=None,
            mean_speed_cm_s=None,
            duration_s=None,
            interval_duration_s=interval_duration,
            edge_gap_s=None,
            interpolated_fraction=None,
            frames_used=0,
            frames_total=total,
            ponto=ponto,
            fps_variavel=fps_variavel,
            speed_caveat=speed_caveat,
            avisos=tuple(avisos),
        )

    valid_times = t_s[valid]
    first, last = float(valid_times[0]), float(valid_times[-1])
    distance = travelled_distance_cm(t_s, x_cm, y_cm, valid, until_s=float(t_s[-1]))
    duration = last - first
    edge_gap = (first - float(t_s[0])) + (float(t_s[-1]) - last)
    speed = None
    if used < 2 or duration <= 0:
        avisos.append(
            f"Só uma amostra válida de {ponto}: distância 0 cm e velocidade não calculada "
            "(não há duração)."
        )
    else:
        speed = distance / duration

    if edge_gap > 0:
        avisos.append(
            f"{ponto} ausente em {edge_gap:.2f} s nas bordas do intervalo útil: a velocidade "
            f"usa {duration:.2f} s (primeiro ao último ponto válido) de {interval_duration:.2f} s."
        )
    interior_missing = int((~valid[(t_s >= first) & (t_s <= last)]).sum())
    if interior_missing:
        avisos.append(
            f"{interior_missing} quadro(s) sem {ponto} dentro do trecho medido, atravessados em "
            "linha reta (subestima um pouco a distância). Ver a qualidade de pose (US-10)."
        )

    return Displacement(
        distance_cm=distance,
        mean_speed_cm_s=speed,
        duration_s=duration,
        interval_duration_s=interval_duration,
        edge_gap_s=edge_gap,
        interpolated_fraction=float(np.mean(interpolated[valid])),
        frames_used=used,
        frames_total=total,
        ponto=ponto,
        fps_variavel=fps_variavel,
        speed_caveat=speed_caveat,
        avisos=tuple(avisos),
    )
