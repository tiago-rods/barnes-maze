"""Entrada física por segmento de ocupação do buraco e hesitação D->E (US-13).

Opera somente na trajetória em cm/eixos de imagem. Cada sequência observada
de quadros consecutivos com o focinho dentro do círculo pode gerar um E. O
instante E é o início da sequência, confirmado apenas quando a duração entre
amostras atinge o limiar. Reentradas são preservadas; a primeira entrada no
alvo fornece as métricas totais do trial na camada que agrega os eventos.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from numbers import Real
from pathlib import Path

import numpy as np
import pyarrow as pa
import yaml

from barnes.events.discovery import DiscoveryEvent
from barnes.geometry.holes import MazeGeometry

DEFAULT_CONFIG_PATH = Path("configs/default.yaml")


class EntryConfigError(ValueError):
    """Critério de entrada ausente, pendente de C2/G3 ou inválido."""


class EntryDetectionError(ValueError):
    """Entradas não podem ser calculadas com os dados fornecidos."""


@dataclass(frozen=True)
class EntryParams:
    """Critério C2 explícito; nenhum limiar numérico tem padrão implícito.

    ``radius_factor`` multiplica o raio físico cadastrado de cada buraco.
    ``minimum_duration_s`` usa tempo observado, não quantidade de quadros.
    A implementação disponível exige ``nose_inside=True``.
    """

    radius_factor: float
    minimum_duration_s: float
    nose_inside: bool = True


@dataclass(frozen=True)
class EntryEvent:
    """Entrada confirmada; distâncias incompletas ficam ausentes com motivo.

    Latências/distâncias delta usam a descoberta inicial do mesmo buraco.
    Descoberta e entrada no mesmo quadro são permitidas pela resolução da
    amostragem: delta é zero. Sem D anterior ou simultâneo, E é preservado,
    os deltas ficam ``None`` e ``issues`` identifica a inconsistência.
    ``total_*`` só existe para o alvo vigente neste trial.
    """

    hole_number: int
    quadro: int
    t_s: float
    confirmed_at_s: float
    delta_latency: float | None
    delta_distance_cm: float | None
    total_latency: float | None
    total_distance_cm: float | None
    discovery_quadro: int | None
    discovery_t_s: float | None
    issues: tuple[str, ...] = ()


def _positive(value: object, name: str, error_type: type[ValueError]) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise error_type(f"'{name}' deve ser um número finito maior que zero.")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise error_type(f"'{name}' excede o intervalo numérico finito suportado.") from exc
    if not math.isfinite(result) or result <= 0:
        raise error_type(f"'{name}' deve ser um número finito maior que zero.")
    return result


def _validate_params(params: EntryParams) -> None:
    _positive(params.radius_factor, "entrar.raio_fator", EntryConfigError)
    _positive(params.minimum_duration_s, "entrar.duracao_minima_s", EntryConfigError)
    if params.nose_inside is not True:
        raise EntryConfigError(
            "'entrar.focinho_dentro' deve ser true para o critério implementado."
        )


def load_entry_params(path: str | Path = DEFAULT_CONFIG_PATH) -> EntryParams:
    """Lê C2 do YAML e recusa valores pendentes sem inventar padrões.

    Raises:
        EntryConfigError: Arquivo/YAML/seção inválida, limiar null/ausente ou
            não positivo/finito, ou critério diferente de focinho dentro.
    """
    path = Path(path)
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise EntryConfigError(f"Não foi possível ler a configuração {path}: {exc}") from exc
    section = document.get("entrar") if isinstance(document, Mapping) else None
    if not isinstance(section, Mapping):
        raise EntryConfigError(f"Seção 'entrar' ausente ou inválida em {path}.")
    for key in ("raio_fator", "duracao_minima_s", "focinho_dentro"):
        if section.get(key) is None:
            raise EntryConfigError(
                f"'entrar.{key}' está vazio em {path}: depende da definição C2/G3 (US-13)."
            )
    params = EntryParams(
        radius_factor=_positive(section["raio_fator"], "entrar.raio_fator", EntryConfigError),
        minimum_duration_s=_positive(
            section["duracao_minima_s"], "entrar.duracao_minima_s", EntryConfigError
        ),
        nose_inside=section["focinho_dentro"],
    )
    _validate_params(params)
    return params


def _columns(table: pa.Table, trial_id: int) -> dict[str, np.ndarray]:
    """Normaliza ordem de quadros; buracos de amostragem permanecem explícitos."""
    required = ("quadro", "t_s", "focinho_x_cm_image", "focinho_y_cm_image", "pose_valida")
    missing = set(required) - set(table.column_names)
    if missing:
        raise EntryDetectionError(
            f"Trial {trial_id}: faltam colunas: {', '.join(sorted(missing))}."
        )
    if not pa.types.is_integer(table.schema.field("quadro").type):
        raise EntryDetectionError(f"Trial {trial_id}: quadro deve conter índices inteiros.")
    if not pa.types.is_boolean(table.schema.field("pose_valida").type):
        raise EntryDetectionError(f"Trial {trial_id}: pose_valida deve ser booleana.")
    for name in ("quadro", "t_s", "pose_valida"):
        if table.column(name).null_count:
            raise EntryDetectionError(f"Trial {trial_id}: coluna {name} contém valores nulos.")
    if "trial_id" in table.column_names:
        ids = table.column("trial_id")
        if ids.null_count or any(value != trial_id for value in ids.to_pylist()):
            raise EntryDetectionError(f"Trial {trial_id}: a trajetória contém outro trial_id.")
    col = {name: table.column(name).to_numpy() for name in required}
    for name in ("t_s", "focinho_x_cm_image", "focinho_y_cm_image"):
        dtype = table.schema.field(name).type
        if not (pa.types.is_floating(dtype) or pa.types.is_integer(dtype)):
            raise EntryDetectionError(f"Trial {trial_id}: coluna {name} deve ser numérica.")
        col[name] = col[name].astype(float)
    order = np.argsort(col["quadro"], kind="stable")
    col = {name: values[order] for name, values in col.items()}
    frames, times = col["quadro"], col["t_s"]
    if (frames < 0).any() or (np.diff(frames) <= 0).any():
        raise EntryDetectionError(f"Trial {trial_id}: quadros negativos ou duplicados.")
    if not np.isfinite(times).all() or (times < 0).any() or (np.diff(times) <= 0).any():
        raise EntryDetectionError(
            f"Trial {trial_id}: t_s deve ser finito, não negativo e crescente com os quadros."
        )
    for axis in ("x", "y"):
        name = f"centro_corpo_{axis}_cm_image"
        if name not in table.column_names:
            col[name] = np.full(len(frames), np.nan)
            continue
        dtype = table.schema.field(name).type
        if not (pa.types.is_floating(dtype) or pa.types.is_integer(dtype)):
            raise EntryDetectionError(f"Trial {trial_id}: coluna {name} deve ser numérica.")
        col[name] = table.column(name).to_numpy().astype(float)[order]
    center_valid = np.isfinite(col["centro_corpo_x_cm_image"]) & np.isfinite(
        col["centro_corpo_y_cm_image"]
    )
    if "centro_corpo_valido" in table.column_names:
        column = table.column("centro_corpo_valido")
        if not pa.types.is_boolean(column.type):
            raise EntryDetectionError(f"Trial {trial_id}: centro_corpo_valido deve ser booleano.")
        # Uma marca ausente não confirma um centro válido para medir distância.
        center_valid &= np.asarray([value is True for value in column.to_pylist()], dtype=bool)[
            order
        ]
    col["center_valid"] = center_valid
    # E depende da localização do focinho, não da orientação da cabeça. Uma
    # falha do centro invalida theta/pose_valida, mas não apaga um focinho
    # observado; as distâncias ficam ausentes quando o centro não é utilizável.
    if "focinho_valido" in table.column_names:
        column = table.column("focinho_valido")
        if not pa.types.is_boolean(column.type):
            raise EntryDetectionError(f"Trial {trial_id}: focinho_valido deve ser booleano.")
        col["nose_valid"] = np.asarray([value is True for value in column.to_pylist()], dtype=bool)[
            order
        ]
    else:
        col["nose_valid"] = col["pose_valida"]
    return col


def _distance(
    col: dict[str, np.ndarray], start: int, end: int, label: str, context: str
) -> tuple[float | None, str | None]:
    """Comprimento integral, recusando lacunas em vez de somar só trechos bons."""
    if not col["center_valid"][start : end + 1].all():
        return None, f"{context}: {label} indisponível: centro_corpo ausente/inválido no trecho."
    if (np.diff(col["quadro"][start : end + 1]) != 1).any():
        return None, f"{context}: {label} indisponível: quadros não consecutivos no trecho."
    x = col["centro_corpo_x_cm_image"][start : end + 1]
    y = col["centro_corpo_y_cm_image"][start : end + 1]
    with np.errstate(over="ignore", invalid="ignore"):
        distance = float(np.hypot(np.diff(x), np.diff(y)).sum())
    if not math.isfinite(distance):
        return None, f"{context}: {label} indisponível: distância calculada não finita."
    return distance, None


def _discovery_map(
    discoveries: Iterable[DiscoveryEvent], holes: set[int], trial_id: int
) -> dict[int, DiscoveryEvent]:
    result = {}
    for event in discoveries:
        if event.hole_number not in holes:
            raise EntryDetectionError(
                f"Trial {trial_id}: descoberta refere buraco inexistente {event.hole_number}."
            )
        if event.hole_number in result:
            raise EntryDetectionError(
                f"Trial {trial_id}, buraco {event.hole_number}: mais de uma descoberta inicial."
            )
        if (
            isinstance(event.quadro, bool)
            or not isinstance(event.quadro, (int, np.integer))
            or event.quadro < 0
            or isinstance(event.t_s, bool)
            or not isinstance(event.t_s, Real)
            or not math.isfinite(event.t_s)
            or event.t_s < 0
        ):
            raise EntryDetectionError(
                f"Trial {trial_id}, buraco {event.hole_number}: quadro/tempo de descoberta inválido."
            )
        result[event.hole_number] = event
    return result


def detect_entries(
    table: pa.Table,
    geometry: MazeGeometry,
    cm_per_px: float,
    params: EntryParams,
    discoveries: Iterable[DiscoveryEvent],
    *,
    trial_id: int,
    target_hole_number: int | None = None,
) -> list[EntryEvent]:
    """Detecta cada segmento de entrada e calcula D->E e S->E sem ler vídeo.

    A fronteira do círculo é interna. Fora do círculo, focinho inválido,
    não finito ou salto de quadro interrompem o segmento. Sem assumir FPS ou
    extrapolar além da última amostra, duração = t_confirmação - t_início.
    ``target_hole_number`` permite aplicar o alvo efetivo após a rotação do
    trial; sem override, usa a marcação da montagem. O chamador seleciona o
    primeiro E desse alvo para as métricas totais do trial.

    A tabela pode vir desordenada e será ordenada por quadro; índices/tempos
    ambíguos são recusados. Centros ausentes não apagam E: somente impedem
    a distância correspondente, com uma indicação de qualidade em ``issues``.
    """
    _validate_params(params)
    scale = _positive(cm_per_px, "cm_per_px", EntryDetectionError)
    if isinstance(trial_id, bool) or not isinstance(trial_id, (int, np.integer)) or trial_id < 1:
        raise EntryDetectionError("trial_id deve ser um inteiro positivo.")
    holes = {hole.hole_number for hole in geometry.holes}
    if len(holes) != len(geometry.holes):
        raise EntryDetectionError(f"Trial {trial_id}: geometria com números de buraco duplicados.")
    if target_hole_number is None:
        targets = [hole.hole_number for hole in geometry.holes if hole.is_target]
        if len(targets) != 1:
            raise EntryDetectionError(f"Trial {trial_id}: a montagem deve ter um único alvo.")
        target_hole_number = targets[0]
    if (
        isinstance(target_hole_number, bool)
        or not isinstance(target_hole_number, (int, np.integer))
        or target_hole_number not in holes
    ):
        raise EntryDetectionError(
            f"Trial {trial_id}: buraco-alvo inexistente {target_hole_number}."
        )
    discovery_by_hole = _discovery_map(discoveries, holes, trial_id)
    col = _columns(table, trial_id)
    frames, times = col["quadro"], col["t_s"]
    frame_positions = {int(frame): index for index, frame in enumerate(frames)}
    nose_valid = (
        col["nose_valid"]
        & np.isfinite(col["focinho_x_cm_image"])
        & np.isfinite(col["focinho_y_cm_image"])
    )
    events = []
    for hole in geometry.holes:
        context = f"Trial {trial_id}, buraco {hole.hole_number}"
        radius = _positive(hole.radius_px, "hole.radius_px", EntryDetectionError)
        if not all(math.isfinite(value) for value in (hole.x_px, hole.y_px)):
            raise EntryDetectionError(f"{context}: centro geométrico não finito.")
        x, y, radius = hole.x_px * scale, hole.y_px * scale, radius * scale * params.radius_factor
        if not all(math.isfinite(value) for value in (x, y, radius)) or radius <= 0:
            raise EntryDetectionError(f"{context}: geometria convertida inválida.")
        inside = nose_valid & (
            np.hypot(col["focinho_x_cm_image"] - x, col["focinho_y_cm_image"] - y) <= radius
        )
        start = None
        emitted = False
        for index, present in enumerate(inside):
            if index and frames[index] != frames[index - 1] + 1:
                start, emitted = None, False
            if not present:
                start, emitted = None, False
                continue
            if start is None:
                start = index
            elapsed = float(times[index] - times[start])
            enough = index > start and (
                elapsed >= params.minimum_duration_s
                or math.isclose(elapsed, params.minimum_duration_s, rel_tol=1e-12, abs_tol=0.0)
            )
            if emitted or not enough:
                continue
            issues = []
            discovery = discovery_by_hole.get(hole.hole_number)
            delta_latency = delta_distance = total_latency = total_distance = None
            if discovery is None:
                issues.append(f"{context}: entrada sem descoberta D anterior ou simultânea.")
            elif discovery.t_s > times[start] or discovery.quadro > frames[start]:
                issues.append(
                    f"{context}: descoberta D posterior à entrada E (inconsistência D->E)."
                )
            else:
                delta_latency = float(times[start] - discovery.t_s)
                d_index = frame_positions.get(discovery.quadro)
                if d_index is None:
                    issues.append(f"{context}: delta_distance_cm indisponível: quadro D ausente.")
                elif not math.isclose(times[d_index], discovery.t_s, rel_tol=1e-12, abs_tol=1e-12):
                    delta_latency = None
                    issues.append(f"{context}: tempo D não corresponde ao quadro na trajetória.")
                else:
                    delta_distance, issue = _distance(
                        col, d_index, start, "delta_distance_cm", context
                    )
                    if issue:
                        issues.append(issue)
            if hole.hole_number == target_hole_number:
                total_latency = float(times[start])
                total_distance, issue = _distance(col, 0, start, "total_distance_cm", context)
                if issue:
                    issues.append(issue)
            events.append(
                EntryEvent(
                    hole_number=hole.hole_number,
                    quadro=int(frames[start]),
                    t_s=float(times[start]),
                    confirmed_at_s=float(times[index]),
                    delta_latency=delta_latency,
                    delta_distance_cm=delta_distance,
                    total_latency=total_latency,
                    total_distance_cm=total_distance,
                    discovery_quadro=discovery.quadro if discovery else None,
                    discovery_t_s=discovery.t_s if discovery else None,
                    issues=tuple(issues),
                )
            )
            emitted = True
    return sorted(events, key=lambda event: (event.t_s, event.hole_number))
