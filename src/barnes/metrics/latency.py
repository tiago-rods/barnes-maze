"""Latência ao buraco-alvo com marcação de censura (US-16).

Função pura, sem banco e sem vídeo: recebe a trajetória do trial
(`barnes.pose.trajectory`, contrato em `docs/contrato-trajetoria.md`), o que os
detectores de evento disseram sobre o buraco-alvo — descoberta D (US-11) e
entrada E (US-13) — e o tempo limite do trial (`trial.tempo_limite_s`, B5), e
devolve as colunas do `trials.csv` do laboratório (US-25):

- `primary_latency` / `primary_distance` / `primary_event`: de S até D (RN01, RN06);
- `total_latency` / `total_distance` / `total_event`: de S até E.

Convenção de censura do pipeline existente (RN02): `*_event = 1` evento observado
dentro do tempo limite; `*_event = 0` censurado, com latência = tempo limite e
distância = percorrida até o tempo limite. Trial censurado **nunca** é descartado:
a função sempre devolve as duas medidas.

Tempo zero é o evento S (RN04): o início do intervalo útil da US-03. A trajetória e
`evento_buraco` já guardam `t_s` nessa referência, então nada é deslocado aqui;
amostras com `t_s` negativo ficam de fora e evento com `t_s` negativo é recusado.

**Detector não executado não é censura.** "O animal não entrou" (o detector de
entrada rodou e não achou E → `total_event = 0`) é diferente de "não sabemos se
entrou" (o detector não rodou → nada calculado, `total_event = None`). Por isso cada
evento chega como `TargetEvent` com três estados explícitos; tratar a ausência do
detector como insucesso produziria uma censura falsa, exatamente o número plausível
e errado que a definição do projeto pede para evitar.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from math import isfinite
from pathlib import Path

import numpy as np
import pyarrow as pa
import yaml

from barnes.events.discovery import DiscoveryEvent

DEFAULT_CONFIG_PATH = Path("configs/default.yaml")

# Pontos do contrato da trajetória; a distância percorrida usa um deles (RN06).
TRAJECTORY_POINTS = ("focinho", "centro_corpo", "base_cauda")
DEFAULT_DISTANCE_POINT = "centro_corpo"

EVENT_OBSERVED = 1
EVENT_CENSORED = 0


class LatencyConfigError(ValueError):
    """`trial.tempo_limite_s` ausente ou inválido em `configs/default.yaml` (RN03)."""


def load_time_limit(path: str | Path = DEFAULT_CONFIG_PATH) -> float:
    """Lê o tempo limite do trial, em segundos (RN03, pergunta B5).

    Args:
        path: Caminho do YAML. Padrão: `configs/default.yaml`, relativo ao
            diretório de trabalho (a raiz do repositório).

    Raises:
        LatencyConfigError: Arquivo ou seção ausente, valor vazio (`null`), não
            numérico ou não positivo. O valor de produção fica `null` até o
            laboratório responder B5; sem ele a censura não é calculada — este
            erro é esperado até lá, não um defeito.
    """
    path = Path(path)
    if not path.is_file():
        raise LatencyConfigError(f"Arquivo de configuração não encontrado: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    section = data.get("trial") if isinstance(data, Mapping) else None
    if not isinstance(section, Mapping):
        raise LatencyConfigError(f"Seção 'trial' ausente em {path}.")
    value = section.get("tempo_limite_s")
    if value is None:
        raise LatencyConfigError(
            "'trial.tempo_limite_s' está vazio em configs/default.yaml: o tempo limite do "
            "trial vem da resposta do laboratório à pergunta B5 e, sem ele, a censura "
            "(primary_event/total_event) não pode ser calculada (US-16 RN02/RN03)."
        )
    if isinstance(value, bool) or not isinstance(value, int | float) or not isfinite(value):
        raise LatencyConfigError("'trial.tempo_limite_s' deve ser um número em segundos.")
    if value <= 0:
        raise LatencyConfigError("'trial.tempo_limite_s' deve ser maior que zero.")
    return float(value)


@dataclass(frozen=True)
class TargetEvent:
    """O que um detector de evento (D ou E) disse sobre o buraco-alvo.

    Três estados, nunca confundidos:

    - `TargetEvent.ocorreu(t)`: o detector rodou e achou o evento em `t` s desde S;
    - `TargetEvent.nao_ocorreu()`: o detector rodou e não achou o evento no trial;
    - `TargetEvent.nao_avaliado()`: o detector não rodou (ex.: US-13 ainda não
      implementada) — a medida correspondente não é calculada.

    Attributes:
        avaliado: O detector foi executado sobre este trial.
        t_s: Segundos desde S (início do intervalo útil), ou `None` sem evento.
    """

    avaliado: bool
    t_s: float | None = None

    def __post_init__(self) -> None:
        if self.t_s is None:
            return
        if not self.avaliado:
            raise ValueError("Evento não avaliado não pode ter tempo.")
        if isinstance(self.t_s, bool) or not isfinite(self.t_s):
            raise ValueError("O tempo do evento deve ser um número finito.")
        if self.t_s < 0:
            raise ValueError(
                f"Evento em t_s={self.t_s} s, antes de S: o tempo zero das latências é o "
                "início do intervalo útil (US-16 RN04). Confira a referência de tempo."
            )

    @classmethod
    def ocorreu(cls, t_s: float) -> TargetEvent:
        return cls(avaliado=True, t_s=float(t_s))

    @classmethod
    def nao_ocorreu(cls) -> TargetEvent:
        return cls(avaliado=True)

    @classmethod
    def nao_avaliado(cls) -> TargetEvent:
        return cls(avaliado=False)


def target_discovery(events: Iterable[DiscoveryEvent], target_hole_number: int) -> TargetEvent:
    """Evento D do buraco-alvo a partir da saída de `detect_discoveries` (US-11 RN05).

    O detector de descoberta rodou, então alvo ausente da lista quer dizer que o
    animal não o descobriu (`nao_ocorreu`), não que faltou avaliar.
    """
    for event in events:
        if event.hole_number == target_hole_number:
            return TargetEvent.ocorreu(event.t_s)
    return TargetEvent.nao_ocorreu()


@dataclass(frozen=True)
class CensoredMeasure:
    """Uma latência com sua versão em distância e a marcação de censura.

    Attributes:
        latency_s: Segundos de S até o evento; tempo limite se censurado;
            `None` se não calculado.
        distance_cm: Distância percorrida de S até o evento (ou até o tempo limite,
            se censurado); `None` se não calculado ou sem pose válida no trecho.
        event: 1 = evento observado, 0 = censurado, `None` = não calculado
            (detector do evento não executado).
    """

    latency_s: float | None
    distance_cm: float | None
    event: int | None

    @property
    def calculado(self) -> bool:
        return self.event is not None


@dataclass(frozen=True)
class TargetLatencies:
    """Latências primária (S→D) e total (S→E) de um trial (US-16).

    Attributes:
        primary: S→D.
        total: S→E.
        tempo_limite_s: Tempo limite usado na censura.
        ponto_distancia: Ponto da trajetória usado na distância percorrida.
        fps_variavel: O vídeo tem fps variável: tempos aproximados (US-01).
        avisos: Ressalvas legíveis (fps variável, evento após o limite,
            inconsistência D/E, medida não calculada, observação curta).
    """

    primary: CensoredMeasure
    total: CensoredMeasure
    tempo_limite_s: float
    ponto_distancia: str
    fps_variavel: bool
    avisos: tuple[str, ...]

    def as_trials_csv(self) -> dict[str, float | int | None]:
        """As seis colunas de latência do `trials.csv` do laboratório (US-25).

        `None` só aparece em medida não calculada (detector ausente) ou em
        distância sem pose válida — nunca no lugar de um trial censurado.
        """
        return {
            "primary_latency": self.primary.latency_s,
            "primary_distance": self.primary.distance_cm,
            "primary_event": self.primary.event,
            "total_latency": self.total.latency_s,
            "total_distance": self.total.distance_cm,
            "total_event": self.total.event,
        }


def travelled_distance_cm(
    t_s: np.ndarray,
    x_cm: np.ndarray,
    y_cm: np.ndarray,
    valid: np.ndarray,
    *,
    until_s: float,
) -> float | None:
    """Distância percorrida de S (t=0) até `until_s`, em cm (RN04, RN06).

    Soma os segmentos entre amostras válidas consecutivas com `0 <= t_s <= until_s`.
    Uma lacuna de pose é atravessada em linha reta entre o último ponto antes e o
    primeiro depois dela (subestima um pouco, nunca inventa trajeto); as lacunas
    longas já ficam sinalizadas pela qualidade de pose (US-10).

    Returns:
        A distância, ou `None` se não há nenhuma amostra válida no trecho
        (distância desconhecida, nunca fabricada como zero).
    """
    keep = valid & (t_s >= 0) & (t_s <= until_s)
    xs = x_cm[keep]
    ys = y_cm[keep]
    if xs.size == 0:
        return None
    return float(np.hypot(np.diff(xs), np.diff(ys)).sum())


def _measure(
    name: str,
    event: TargetEvent,
    tempo_limite_s: float,
    distance_until: Callable[[float], float | None],
    avisos: list[str],
) -> CensoredMeasure:
    if not event.avaliado:
        detector = "descoberta (D, US-11)" if name == "primary" else "entrada (E, US-13)"
        avisos.append(
            f"{name}_*: não calculado — o detector de {detector} não foi executado. "
            "Isto não é censura: não se sabe se o evento ocorreu."
        )
        return CensoredMeasure(latency_s=None, distance_cm=None, event=None)
    if event.t_s is not None and event.t_s <= tempo_limite_s:
        return CensoredMeasure(
            latency_s=event.t_s, distance_cm=distance_until(event.t_s), event=EVENT_OBSERVED
        )
    if event.t_s is not None:
        avisos.append(
            f"{name}_*: evento em {event.t_s:.2f} s, depois do tempo limite de "
            f"{tempo_limite_s:g} s — tratado como censurado."
        )
    return CensoredMeasure(
        latency_s=tempo_limite_s, distance_cm=distance_until(tempo_limite_s), event=EVENT_CENSORED
    )


def compute_target_latencies(
    trajectory: pa.Table,
    discovery: TargetEvent,
    entry: TargetEvent,
    *,
    tempo_limite_s: float,
    ponto_distancia: str = DEFAULT_DISTANCE_POINT,
) -> TargetLatencies:
    """Latências e distâncias S→D e S→E do buraco-alvo, com censura (RN01-RN06).

    Args:
        trajectory: Trajetória do trial (`read_trajectory`): usa `t_s`,
            `<ponto>_x_cm_image`, `<ponto>_y_cm_image`, `<ponto>_valido` e
            `fps_variavel`.
        discovery: Evento D do alvo (`target_discovery`).
        entry: Evento E do alvo. Enquanto a US-13 não existir, passe
            `TargetEvent.nao_avaliado()`: as colunas `total_*` saem `None`.
        tempo_limite_s: Tempo limite do trial (`load_time_limit`), explícito para
            que nenhum chamador censure com um valor implícito.
        ponto_distancia: Ponto do corpo usado na distância percorrida.

    Returns:
        As duas medidas. Um trial censurado sempre sai com latência = tempo limite
        e `event = 0`, nunca é omitido.

    Raises:
        ValueError: Tempo limite não positivo, ponto desconhecido ou trajetória
            sem as colunas necessárias.
    """
    if (
        isinstance(tempo_limite_s, bool)
        or not isinstance(tempo_limite_s, int | float)
        or not isfinite(tempo_limite_s)
        or tempo_limite_s <= 0
    ):
        raise ValueError("O tempo limite do trial deve ser um número positivo, em segundos.")
    tempo_limite_s = float(tempo_limite_s)
    if ponto_distancia not in TRAJECTORY_POINTS:
        raise ValueError(
            f"Ponto '{ponto_distancia}' desconhecido; use um de {', '.join(TRAJECTORY_POINTS)}."
        )
    columns = (
        "t_s",
        f"{ponto_distancia}_x_cm_image",
        f"{ponto_distancia}_y_cm_image",
        f"{ponto_distancia}_valido",
        "fps_variavel",
    )
    missing = [name for name in columns if name not in trajectory.column_names]
    if missing:
        raise ValueError(f"Trajetória sem as colunas: {', '.join(missing)}.")
    t_s, x_cm, y_cm, valid, fps = (trajectory.column(name).to_numpy() for name in columns)
    fps_variavel = bool(fps.any())

    def distance_until(until_s: float) -> float | None:
        return travelled_distance_cm(t_s, x_cm, y_cm, valid.astype(bool), until_s=until_s)

    avisos: list[str] = []
    if fps_variavel:
        avisos.append("Vídeo com fps variável (US-01): latências e distâncias são aproximadas.")
    primary = _measure("primary", discovery, tempo_limite_s, distance_until, avisos)
    total = _measure("total", entry, tempo_limite_s, distance_until, avisos)

    if entry.t_s is not None and discovery.avaliado:
        if discovery.t_s is None:
            avisos.append("Inconsistência: entrada no alvo sem descoberta do alvo (US-13 RN03).")
        elif entry.t_s < discovery.t_s:
            avisos.append(
                f"Inconsistência: entrada no alvo ({entry.t_s:.2f} s) antes da descoberta "
                f"({discovery.t_s:.2f} s) (US-13 RN03)."
            )

    censored = EVENT_CENSORED in (primary.event, total.event)
    observed_until = float(t_s.max()) if t_s.size else 0.0
    if censored and observed_until < tempo_limite_s:
        avisos.append(
            f"A trajetória termina em {observed_until:.2f} s, antes do tempo limite de "
            f"{tempo_limite_s:g} s: a censura no tempo limite supõe observação até lá, e a "
            "distância censurada vai só até o fim da trajetória. Confira o intervalo útil."
        )

    return TargetLatencies(
        primary=primary,
        total=total,
        tempo_limite_s=tempo_limite_s,
        ponto_distancia=ponto_distancia,
        fps_variavel=fps_variavel,
        avisos=tuple(avisos),
    )
