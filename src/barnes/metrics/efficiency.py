"""Índice de eficiência de rota até o buraco-alvo (US-19).

Função pura, sem banco e sem vídeo: recebe a trajetória do trial
(`barnes.pose.trajectory`, contrato em `docs/contrato-trajetoria.md`) e uma medida
censurada da US-16 (`barnes.metrics.latency.CensoredMeasure`, S→D ou S→E), e devolve

    índice = distância percorrida até o alvo / distância mínima da soltura ao alvo

(RN01). Valor mínimo teórico 1,0 = rota ideal; quanto maior, mais excesso de
percurso. **Não confundir** com o `route_efficiency` da US-02
(função `barnes.metrics.route_efficiency`, coluna `trial_results.route_efficiency`), que é
a razão inversa, ideal / percorrida, em [0, 1], sobre o trajeto inteiro.

Convenções (nota de implementação em `docs/definicoes-metricas.md`, "Eficiência de
rota"; decisões da equipe, sem resposta do laboratório):

- **Ponto de soltura** (RN02, SCRUM-228): a posição do ponto do corpo na **primeira
  amostra válida do intervalo útil** (`t_s >= 0`). O intervalo começa em S, a
  retirada do cilindro (US-03 RN03, `docs/decisoes-sem-laboratorio.md` §2), então
  essa é a posição em que o animal foi solto — medida no vídeo, nunca suposta no
  centro da plataforma (B3 continua aberta). A distância ao centro da plataforma sai
  junto, para auditoria. Se a pose falta no começo, a soltura é a primeira amostra
  com pose e o atraso sai em aviso. Nenhum parâmetro novo.
- **Distância mínima** (SCRUM-229): linha reta, em cm, da soltura ao **ponto de
  chegada**, a posição do mesmo ponto do corpo na última amostra válida até o evento
  (D ou E) do alvo. Não é a distância ao centro do buraco: o evento é detectado pelo
  focinho, e o centro do corpo para alguns cm antes do buraco. Comparado com o
  centro do buraco, um trajeto reto daria índice < 1,0. Medindo os dois extremos com
  o mesmo ponto, a desigualdade triangular garante índice >= 1,0. A distância da
  soltura ao centro do buraco-alvo também sai, para auditoria.
- **Distância percorrida** (SCRUM-230): a mesma da US-16
  (`metrics.latency.travelled_distance_cm`: soma dos segmentos do ponto entre amostras
  válidas, com lacunas atravessadas em linha reta), de S até o evento.
- **Censura** (RN03, SCRUM-231): evento censurado (`event = 0`) ou não calculado
  (`event = None`) → índice `None`, nunca um valor arbitrário. Distância mínima zero
  (chegada no próprio ponto de soltura) → índice `None` com aviso: a razão não é
  definida.
- **Sanidade** (RN05, SCRUM-233): índice < 1,0 indica erro de cálculo. É recusado com
  `RouteEfficiencyError`, com a tolerância numérica `SANITY_TOLERANCE`.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite

import numpy as np
import pyarrow as pa

from barnes.geometry.holes import MazeGeometry
from barnes.metrics.latency import (
    DEFAULT_DISTANCE_POINT,
    EVENT_CENSORED,
    EVENT_OBSERVED,
    TRAJECTORY_POINTS,
    CensoredMeasure,
    TargetLatencies,
    travelled_distance_cm,
)

# Tolerância RELATIVA do teste de sanidade (RN05). Em aritmética exata o índice é
# >= 1 (desigualdade triangular). Em ponto flutuante, a soma de n segmentos acumula
# um erro relativo da ordem de n · 2,2e-16: ~1e-12 num trial de 180 s a 25 fps
# (4.500 segmentos) e ~2e-11 com 10^5. 1e-9 cobre isso com folga, e um erro de
# cálculo real (ponto ou escala trocados, trecho errado) fica muitas ordens de
# grandeza acima. É tolerância numérica, não limiar do laboratório: fica no código,
# como o r >= 0,95 de `metrics.validation`.
SANITY_TOLERANCE = 1e-9

# Colunas complementares do `trials.csv` (US-25 RN04, ao final do arquivo). Distâncias
# em cm aqui; a exportação da US-25 converte para metros.
EXPORT_COLUMNS = (
    "primary_route_efficiency",
    "total_route_efficiency",
    "release_x_cm_image",
    "release_y_cm_image",
    "release_t_s",
    "release_center_distance_cm",
)


class RouteEfficiencyError(ValueError):
    """Índice abaixo de 1,0, ou entradas incoerentes: erro de cálculo (US-19 RN05)."""


def _finite_nonnegative(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not isfinite(value):
        raise RouteEfficiencyError(f"{name} deve ser um número finito.")
    if value < 0:
        raise RouteEfficiencyError(f"{name} não pode ser negativa ({value}).")
    return float(value)


def validate_route_efficiency(indice: float, *, tolerance: float = SANITY_TOLERANCE) -> float:
    """Teste de sanidade do índice (RN05, Cenário 4, SCRUM-233).

    Args:
        indice: Índice calculado.
        tolerance: Tolerância relativa abaixo de 1,0 aceita como arredondamento.

    Returns:
        O próprio índice, se passar.

    Raises:
        RouteEfficiencyError: Índice não finito ou menor que `1 − tolerance`.
    """
    if isinstance(indice, bool) or not isinstance(indice, int | float) or not isfinite(indice):
        raise RouteEfficiencyError(f"Índice de eficiência de rota não finito: {indice!r}.")
    if indice < 1.0 - tolerance:
        raise RouteEfficiencyError(
            f"Índice de eficiência de rota {indice:.12g} < 1,0: a distância percorrida não "
            "pode ser menor que a linha reta entre os mesmos dois pontos. Erro de cálculo "
            "(US-19 RN05): confira o ponto do corpo, a escala e o trecho usados."
        )
    return float(indice)


def route_efficiency_index(distancia_percorrida_cm: float, distancia_minima_cm: float) -> float:
    """Razão distância percorrida / distância mínima, já validada (RN01, RN05).

    Raises:
        RouteEfficiencyError: Distância negativa ou não finita, distância mínima zero
            (razão indefinida) ou índice < 1,0.
    """
    percorrida = _finite_nonnegative(distancia_percorrida_cm, "A distância percorrida")
    minima = _finite_nonnegative(distancia_minima_cm, "A distância mínima")
    if minima == 0:
        raise RouteEfficiencyError(
            "Distância mínima zero: a chegada coincide com a soltura e o índice não é definido."
        )
    return validate_route_efficiency(percorrida / minima)


@dataclass(frozen=True)
class ReleasePoint:
    """Ponto de soltura detectado na trajetória (RN02, RN04).

    Attributes:
        x_cm_image: Posição x, em cm, eixos da imagem (US-05 RN05).
        y_cm_image: Posição y, em cm, eixos da imagem.
        t_s: Tempo da amostra, em segundos desde S; > 0 quando falta pose no começo.
        quadro: Quadro do vídeo da amostra, se a trajetória tem a coluna `quadro`.
        ponto: Ponto do corpo usado.
        distancia_centro_cm: Distância ao centro da plataforma, em cm, se a geometria
            foi informada (auditoria do Cenário 1); `None` caso contrário.
    """

    x_cm_image: float
    y_cm_image: float
    t_s: float
    quadro: int | None
    ponto: str
    distancia_centro_cm: float | None


def _columns(trajectory: pa.Table, ponto: str) -> tuple[np.ndarray, ...]:
    if ponto not in TRAJECTORY_POINTS:
        raise ValueError(f"Ponto '{ponto}' desconhecido; use um de {', '.join(TRAJECTORY_POINTS)}.")
    names = ("t_s", f"{ponto}_x_cm_image", f"{ponto}_y_cm_image", f"{ponto}_valido")
    missing = [name for name in names if name not in trajectory.column_names]
    if missing:
        raise ValueError(f"Trajetória sem as colunas: {', '.join(missing)}.")
    t_s, x, y, valid = (trajectory.column(name).to_numpy() for name in names)
    return t_s, x, y, valid.astype(bool)


def _cm(geometry: MazeGeometry | None, cm_per_px: float | None) -> tuple:
    if (geometry is None) != (cm_per_px is None):
        raise ValueError("Informe a geometria e a escala (cm_per_px) juntas, ou nenhuma das duas.")
    if geometry is None:
        return None, None
    if isinstance(cm_per_px, bool) or not isfinite(cm_per_px) or cm_per_px <= 0:
        raise ValueError("cm_per_px deve ser um número positivo.")
    centro = (geometry.center_x_px * cm_per_px, geometry.center_y_px * cm_per_px)
    alvo = geometry.target_hole
    return centro, (alvo.x_px * cm_per_px, alvo.y_px * cm_per_px)


def detect_release_point(
    trajectory: pa.Table,
    *,
    ponto: str = DEFAULT_DISTANCE_POINT,
    geometry: MazeGeometry | None = None,
    cm_per_px: float | None = None,
) -> ReleasePoint | None:
    """Ponto de soltura do trial: primeira amostra válida do ponto em `t_s >= 0` (RN02).

    Args:
        trajectory: Trajetória do trial (`read_trajectory`).
        ponto: Ponto do corpo (o mesmo da distância percorrida).
        geometry: Montagem do trial, só para a distância ao centro (auditoria).
        cm_per_px: Escala da montagem, obrigatória junto com `geometry`.

    Returns:
        O ponto de soltura, ou `None` se não há nenhuma amostra válida do ponto
        (soltura desconhecida, nunca suposta no centro).
    """
    t_s, x, y, valid = _columns(trajectory, ponto)
    centro, _ = _cm(geometry, cm_per_px)
    candidates = np.flatnonzero(valid & (t_s >= 0))
    if candidates.size == 0:
        return None
    i = int(candidates[0])
    quadro = (
        int(trajectory.column("quadro")[i].as_py()) if "quadro" in trajectory.column_names else None
    )
    rx, ry = float(x[i]), float(y[i])
    return ReleasePoint(
        x_cm_image=rx,
        y_cm_image=ry,
        t_s=float(t_s[i]),
        quadro=quadro,
        ponto=ponto,
        distancia_centro_cm=None if centro is None else hypot(rx - centro[0], ry - centro[1]),
    )


@dataclass(frozen=True)
class RouteEfficiency:
    """Índice de eficiência de rota de uma medida (S→D ou S→E), com o que o audita.

    Attributes:
        indice: Distância percorrida / distância mínima; `None` se censurado, não
            calculado, sem pose ou com distância mínima zero.
        evento: 1 = alvo alcançado, 0 = censurado, `None` = não calculado (como na
            US-16).
        latencia_s: Tempo do evento (ou o tempo limite, se censurado), da US-16.
        distancia_percorrida_cm: Da soltura à chegada; `None` sem índice.
        distancia_minima_cm: Linha reta da soltura à chegada; `None` sem índice.
        chegada_x_cm_image: Ponto de chegada, x em cm; `None` sem índice.
        chegada_y_cm_image: Ponto de chegada, y em cm; `None` sem índice.
        chegada_t_s: Tempo da amostra de chegada; `None` sem índice.
        distancia_soltura_alvo_cm: Linha reta da soltura ao centro do buraco-alvo,
            se a geometria foi informada (auditoria); `None` caso contrário.
        avisos: Ressalvas legíveis.
    """

    indice: float | None
    evento: int | None
    latencia_s: float | None
    distancia_percorrida_cm: float | None
    distancia_minima_cm: float | None
    chegada_x_cm_image: float | None
    chegada_y_cm_image: float | None
    chegada_t_s: float | None
    distancia_soltura_alvo_cm: float | None
    avisos: tuple[str, ...]

    @property
    def calculado(self) -> bool:
        return self.indice is not None


def _absent(measure: CensoredMeasure, distancia_alvo: float | None, aviso: str) -> RouteEfficiency:
    return RouteEfficiency(
        indice=None,
        evento=measure.event,
        latencia_s=measure.latency_s,
        distancia_percorrida_cm=None,
        distancia_minima_cm=None,
        chegada_x_cm_image=None,
        chegada_y_cm_image=None,
        chegada_t_s=None,
        distancia_soltura_alvo_cm=distancia_alvo,
        avisos=(aviso,),
    )


def compute_route_efficiency(
    trajectory: pa.Table,
    measure: CensoredMeasure,
    *,
    ponto: str = DEFAULT_DISTANCE_POINT,
    release: ReleasePoint | None = None,
    geometry: MazeGeometry | None = None,
    cm_per_px: float | None = None,
    nome: str = "indice",
) -> RouteEfficiency:
    """Índice de eficiência de rota até o evento de `measure` (RN01, RN03, RN05).

    Args:
        trajectory: Trajetória do trial (`read_trajectory`).
        measure: Medida censurada da US-16 (`TargetLatencies.primary` = S→D ou
            `.total` = S→E). Ela decide se o alvo foi alcançado: o índice não
            reimplementa a regra de censura.
        ponto: Ponto do corpo; deve ser o mesmo da medida (`ponto_distancia`).
        release: Ponto de soltura já detectado; padrão: `detect_release_point`.
        geometry: Montagem, para as distâncias de auditoria ao centro e ao alvo.
        cm_per_px: Escala da montagem, junto com `geometry`.
        nome: Prefixo das mensagens (ex.: `primary_route_efficiency`).

    Returns:
        O índice e o que o audita. Censurado ou não calculado → índice `None`.

    Raises:
        RouteEfficiencyError: Índice < 1,0 (erro de cálculo, RN05).
        ValueError: Ponto desconhecido ou trajetória sem as colunas.
    """
    t_s, x, y, valid = _columns(trajectory, ponto)
    if release is None:
        release = detect_release_point(
            trajectory, ponto=ponto, geometry=geometry, cm_per_px=cm_per_px
        )
    elif release.ponto != ponto:
        raise ValueError(f"Soltura medida com '{release.ponto}', índice pedido com '{ponto}'.")
    _, alvo = _cm(geometry, cm_per_px)
    distancia_alvo = (
        None
        if alvo is None or release is None
        else hypot(alvo[0] - release.x_cm_image, alvo[1] - release.y_cm_image)
    )

    if measure.event is None:
        return _absent(
            measure,
            distancia_alvo,
            f"{nome}: não calculado — a medida da US-16 não foi calculada (detector não "
            "executado). Não é censura nem índice zero.",
        )
    if measure.event == EVENT_CENSORED:
        return _absent(
            measure,
            distancia_alvo,
            f"{nome}: ausente — trial censurado, o alvo não foi alcançado até "
            f"{measure.latency_s:g} s (US-19 RN03).",
        )
    if measure.event != EVENT_OBSERVED or measure.latency_s is None:
        raise ValueError(f"Medida da US-16 inconsistente: event={measure.event!r}.")
    if release is None:
        return _absent(
            measure,
            distancia_alvo,
            f"{nome}: não calculado — nenhuma amostra válida de {ponto}: o ponto de soltura "
            "é desconhecido (não se supõe o centro).",
        )

    until = measure.latency_s
    upto = np.flatnonzero(valid & (t_s >= 0) & (t_s <= until))
    if upto.size == 0:  # a primeira pose válida (a soltura) veio depois do evento
        return _absent(
            measure,
            distancia_alvo,
            f"{nome}: não calculado — sem amostra válida de {ponto} até o evento ({until:g} s).",
        )
    j = int(upto[-1])
    chegada = (float(x[j]), float(y[j]))
    minima = hypot(chegada[0] - release.x_cm_image, chegada[1] - release.y_cm_image)
    percorrida = travelled_distance_cm(t_s, x, y, valid, until_s=until)

    avisos: list[str] = []
    if release.t_s > 0:
        avisos.append(
            f"{nome}: {ponto} ausente no início do intervalo útil; a soltura é a primeira "
            f"amostra com pose, em {release.t_s:.2f} s depois de S."
        )
    if minima == 0:
        avisos.append(
            f"{nome}: não calculado — a chegada coincide com o ponto de soltura (distância "
            "mínima zero): a razão não é definida."
        )
        indice = None
    else:
        indice = route_efficiency_index(percorrida, minima)

    return RouteEfficiency(
        indice=indice,
        evento=measure.event,
        latencia_s=measure.latency_s,
        distancia_percorrida_cm=percorrida,
        distancia_minima_cm=minima,
        chegada_x_cm_image=chegada[0],
        chegada_y_cm_image=chegada[1],
        chegada_t_s=float(t_s[j]),
        distancia_soltura_alvo_cm=distancia_alvo,
        avisos=tuple(avisos),
    )


@dataclass(frozen=True)
class TrialRouteEfficiency:
    """Índices S→D (`primary`) e S→E (`total`) de um trial, com a soltura (RN04).

    Attributes:
        soltura: Ponto de soltura detectado; `None` sem pose válida.
        primary: Índice até a descoberta do alvo (D, US-11), como `primary_*`.
        total: Índice até a entrada no alvo (E, US-13), como `total_*`.
        ponto: Ponto do corpo usado.
    """

    soltura: ReleasePoint | None
    primary: RouteEfficiency
    total: RouteEfficiency
    ponto: str

    @property
    def avisos(self) -> tuple[str, ...]:
        return self.primary.avisos + self.total.avisos

    def as_trial_results(self) -> dict[str, float | None]:
        """Colunas complementares do `trials.csv` (US-25 RN04), com a soltura (RN04).

        Índices adimensionais; posição e distância em **cm** (a US-25 converte para
        metros). `None` só em índice ausente (censura, medida não calculada, sem pose)
        ou sem a informação de auditoria — nunca um valor arbitrário.
        """
        soltura = self.soltura
        return {
            "primary_route_efficiency": self.primary.indice,
            "total_route_efficiency": self.total.indice,
            "release_x_cm_image": None if soltura is None else soltura.x_cm_image,
            "release_y_cm_image": None if soltura is None else soltura.y_cm_image,
            "release_t_s": None if soltura is None else soltura.t_s,
            "release_center_distance_cm": None if soltura is None else soltura.distancia_centro_cm,
        }


def compute_trial_route_efficiency(
    trajectory: pa.Table,
    latencies: TargetLatencies,
    *,
    geometry: MazeGeometry | None = None,
    cm_per_px: float | None = None,
) -> TrialRouteEfficiency:
    """Índices S→D e S→E a partir das latências da US-16, com o mesmo ponto do corpo.

    Args:
        trajectory: A mesma trajetória usada em `compute_target_latencies`.
        latencies: Resultado de `compute_target_latencies` (censura já decidida).
        geometry: Montagem do trial, para as distâncias de auditoria.
        cm_per_px: Escala da montagem, junto com `geometry`.
    """
    ponto = latencies.ponto_distancia
    release = detect_release_point(trajectory, ponto=ponto, geometry=geometry, cm_per_px=cm_per_px)
    common = {"ponto": ponto, "release": release, "geometry": geometry, "cm_per_px": cm_per_px}
    return TrialRouteEfficiency(
        soltura=release,
        primary=compute_route_efficiency(
            trajectory, latencies.primary, nome="primary_route_efficiency", **common
        ),
        total=compute_route_efficiency(
            trajectory, latencies.total, nome="total_route_efficiency", **common
        ),
        ponto=ponto,
    )
