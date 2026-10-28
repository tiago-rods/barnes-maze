"""Qualidade da pose por trial: suavização, lacunas, cobertura e correções (US-10).

Funções puras, sem banco, GPU nem janela: recebem a pose bruta da inferência em
**pixels** (`barnes.pose.series.PoseFrames`), as correções manuais e os
parâmetros de `configs/default.yaml`, e devolvem a pose tratada mais o relatório
de qualidade. A conversão para cm, a validade de cada ponto e θ continuam sendo
calculadas só em `barnes.pose.series.build_series`. A mediana móvel e a
interpolação linear dão o mesmo resultado antes ou depois de multiplicar pela
escala única px→cm, então tratar em pixels não muda nada. A orquestração (ler as
correções do banco, registrar a execução, gravar a série) fica na CLI.

Ordem do tratamento, sempre a mesma (`postprocess_pose`):

1. **correções manuais** (RN05) sobrepõem o ponto no quadro marcado;
2. **suavização** por mediana móvel, só dentro de trechos contínuos com o ponto,
   sem atravessar lacuna;
3. **interpolação** linear das lacunas **curtas** (RN01): até
   `lacuna_curta_max_quadros` quadros seguidos sem o ponto, com o ponto presente
   nos dois lados. A linha preenchida fica com `interpolado = true`;
4. **sinalização** das lacunas que sobram (RN02). São as longas e as que tocam a
   borda do intervalo útil, que não têm um dos lados para interpolar;
5. **cobertura** (RN03): fração dos quadros com os três pontos, contando os
   interpolados e os corrigidos. A cobertura só da detecção vai junto no relatório.

As lacunas são detectadas **por ponto**: faltar a base da cauda por dois quadros
preenche só a base da cauda.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from barnes.pose.annotations import KEYPOINTS
from barnes.pose.series import PoseFrames

DEFAULT_CONFIG_PATH = Path("configs/default.yaml")
SMOOTHING_METHODS = ("mediana",)

FPS_VARIABLE_CAVEAT = (
    "Interpolação num vídeo com fps variável (US-01): os quadros são interpolados por "
    "índice e os tempos t_s do trial são aproximados, então a posição interpolada também "
    "é menos exata (US-10 RN07)."
)


class QualityConfigError(ValueError):
    """Seção `pose` ausente ou inválida em `configs/default.yaml`."""


class PoseQuality(StrEnum):
    """Qualidade de pose de um trial (RN06), derivada da cobertura e das pendências."""

    SUFICIENTE = "suficiente"
    REVISAO_PENDENTE = "revisao_pendente"
    INSUFICIENTE = "insuficiente"


@dataclass(frozen=True)
class QualityParams:
    """Parâmetros de tratamento da pose (seção `pose` de `configs/default.yaml`).

    Attributes:
        min_coverage: Cobertura mínima para o trial ter qualidade suficiente (RN03).
        short_gap_max_frames: Maior lacuna, em quadros, que ainda é interpolada (RN01).
        smoothing_method: Método de suavização (só "mediana" por enquanto).
        smoothing_window: Janela da suavização, em quadros (ímpar; 1 = sem suavização).
    """

    min_coverage: float
    short_gap_max_frames: int
    smoothing_method: str
    smoothing_window: int

    def as_record(self) -> dict[str, Any]:
        """Os parâmetros com os nomes do YAML, para registrar na execução."""
        return {
            "cobertura_minima": self.min_coverage,
            "lacuna_curta_max_quadros": self.short_gap_max_frames,
            "suavizacao": {
                "metodo": self.smoothing_method,
                "janela_quadros": self.smoothing_window,
            },
        }


def _value(section: Mapping, key: str, where: str) -> Any:
    value = section.get(key) if isinstance(section, Mapping) else None
    if value is None:
        raise QualityConfigError(
            f"'{where}.{key}' está vazio em configs/default.yaml: defina o valor (US-10)."
        )
    return value


def _number(section: Mapping, key: str, where: str) -> float:
    value = _value(section, key, where)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise QualityConfigError(f"'{where}.{key}' deve ser um número em configs/default.yaml.")
    return float(value)


def _integer(section: Mapping, key: str, where: str) -> int:
    value = _value(section, key, where)
    if isinstance(value, bool) or not isinstance(value, int):
        raise QualityConfigError(
            f"'{where}.{key}' deve ser um número inteiro de quadros em configs/default.yaml."
        )
    return value


def load_quality_params(path: str | Path = DEFAULT_CONFIG_PATH) -> QualityParams:
    """Lê e valida a seção `pose` do arquivo de configuração (SCRUM-125).

    Args:
        path: Caminho do YAML. Padrão: `configs/default.yaml`, relativo ao
            diretório de trabalho (a raiz do repositório).

    Raises:
        QualityConfigError: Arquivo ou seção ausente, valor vazio (`null`) ou
            fora da faixa — a mensagem nomeia a chave.
    """
    path = Path(path)
    if not path.is_file():
        raise QualityConfigError(f"Arquivo de configuração não encontrado: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    section = data.get("pose") if isinstance(data, Mapping) else None
    if not isinstance(section, Mapping):
        raise QualityConfigError(f"Seção 'pose' ausente em {path}.")

    minimum = _number(section, "cobertura_minima", "pose")
    if not 0 < minimum <= 1:
        raise QualityConfigError("'pose.cobertura_minima' deve estar entre 0 (exclusive) e 1.")
    short_gap = _integer(section, "lacuna_curta_max_quadros", "pose")
    if short_gap < 0:
        raise QualityConfigError("'pose.lacuna_curta_max_quadros' não pode ser negativo.")

    smoothing = section.get("suavizacao")
    if not isinstance(smoothing, Mapping):
        raise QualityConfigError(f"Seção 'pose.suavizacao' ausente em {path}.")
    method = _value(smoothing, "metodo", "pose.suavizacao")
    if method not in SMOOTHING_METHODS:
        raise QualityConfigError(
            f"'pose.suavizacao.metodo' deve ser um de: {', '.join(SMOOTHING_METHODS)}."
        )
    window = _integer(smoothing, "janela_quadros", "pose.suavizacao")
    if window < 1 or window % 2 == 0:
        raise QualityConfigError(
            "'pose.suavizacao.janela_quadros' deve ser ímpar e maior ou igual a 1."
        )
    return QualityParams(minimum, short_gap, method, window)


# --- Lacunas -----------------------------------------------------------------


@dataclass(frozen=True)
class Gap:
    """Trecho contínuo de linhas sem um ponto.

    Attributes:
        start: Primeira linha sem o ponto (posição na série, a partir de 0).
        end: Última linha sem o ponto, inclusive.
        at_edge: Toca o início ou o fim da série: falta um dos lados para interpolar.
    """

    start: int
    end: int
    at_edge: bool

    @property
    def length(self) -> int:
        """Quantidade de quadros da lacuna."""
        return self.end - self.start + 1


def find_gaps(valid: np.ndarray) -> list[Gap]:
    """Lacunas (trechos contínuos de `False`) de uma máscara de validade, em ordem."""
    missing = ~np.asarray(valid, dtype=bool)
    if not missing.any():
        return []
    edges = np.diff(np.concatenate(([0], missing.astype(np.int8), [0])))
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1) - 1
    last = len(missing) - 1
    return [
        Gap(int(start), int(end), bool(start == 0 or end == last))
        for start, end in zip(starts, ends, strict=True)
    ]


def _valid(pose: PoseFrames, point: str) -> np.ndarray:
    return np.isfinite(pose.x_px[point]) & np.isfinite(pose.y_px[point])


def _present_runs(valid: np.ndarray) -> list[tuple[int, int]]:
    """Trechos contínuos de `True`, como (início, fim exclusive)."""
    edges = np.diff(np.concatenate(([0], np.asarray(valid, dtype=np.int8), [0])))
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1), strict=True))


# --- Suavização (SCRUM-126) --------------------------------------------------


def _centered_median(values: np.ndarray, window: int) -> np.ndarray:
    """Mediana móvel centrada cuja janela encolhe simetricamente nas pontas.

    O quadro `i` usa a maior janela ímpar centrada nele que cabe no trecho:
    `min(window // 2, i, n - 1 - i)` vizinhos de cada lado. O primeiro e o
    último quadro do trecho ficam como estão. Uma janela assimétrica deslocaria
    justamente os quadros vizinhos de uma lacuna, que são os pontos de apoio da
    interpolação, e um movimento retilíneo não ficaria preservado.
    """
    smoothed = values.copy()
    for half in range(1, window // 2 + 1):
        if len(values) < 2 * half + 1:
            break
        windows = np.lib.stride_tricks.sliding_window_view(values, 2 * half + 1)
        smoothed[half : len(values) - half] = np.median(windows, axis=1)
    return smoothed


def smooth_points(pose: PoseFrames, window: int) -> PoseFrames:
    """Suaviza cada ponto com mediana móvel centrada, sem atravessar lacunas.

    A mediana é calculada só dentro de cada trecho contínuo em que o ponto
    existe; nas pontas do trecho a janela encolhe simetricamente
    (`_centered_median`). Um ponto ausente continua ausente: suavizar nunca
    preenche. A mediana remove um quadro isolado muito fora (troca momentânea
    de ponto) sem arrastar a posição como uma média faria, e preserva um
    movimento retilíneo.

    Args:
        pose: Pose em pixels.
        window: Janela em quadros, ímpar; 1 devolve a pose sem mudança.

    Raises:
        ValueError: Se a janela não for um inteiro ímpar positivo.
    """
    if isinstance(window, bool) or not isinstance(window, int) or window < 1 or window % 2 == 0:
        raise ValueError("A janela de suavização deve ser um inteiro ímpar maior ou igual a 1.")
    if window == 1:
        return pose
    x, y = {}, {}
    for point in KEYPOINTS:
        xs, ys = pose.x_px[point].astype(np.float64), pose.y_px[point].astype(np.float64)
        for start, end in _present_runs(_valid(pose, point)):
            xs[start:end] = _centered_median(xs[start:end], window)
            ys[start:end] = _centered_median(ys[start:end], window)
        x[point], y[point] = xs, ys
    return replace(pose, x_px=x, y_px=y)


# --- Interpolação de lacunas curtas (SCRUM-128) ------------------------------


def interpolate_short_gaps(pose: PoseFrames, max_frames: int) -> tuple[PoseFrames, np.ndarray]:
    """Preenche por interpolação linear as lacunas curtas de cada ponto (RN01).

    Só é preenchida a lacuna com até `max_frames` quadros **e** com o ponto
    presente imediatamente antes e depois. Lacuna maior, ou na borda da série,
    fica como está (é sinalizada por `flag_long_gaps`). A interpolação usa o
    índice do quadro, não `t_s` (ver `FPS_VARIABLE_CAVEAT`). A confiança do
    modelo não é inventada e continua NaN nos quadros preenchidos.

    Returns:
        A pose preenchida e a máscara das linhas em que algum ponto foi
        interpolado (vai para a coluna `interpolado` da série).
    """
    if isinstance(max_frames, bool) or not isinstance(max_frames, int) or max_frames < 0:
        raise ValueError("O limite de lacuna curta deve ser um inteiro maior ou igual a zero.")
    frames = pose.frames.astype(np.float64)
    interpolated = np.zeros(len(pose.frames), dtype=bool)
    x, y = {}, {}
    for point in KEYPOINTS:
        xs, ys = pose.x_px[point].astype(np.float64), pose.y_px[point].astype(np.float64)
        for gap in find_gaps(_valid(pose, point)):
            if gap.at_edge or gap.length > max_frames:
                continue
            before, after = gap.start - 1, gap.end + 1
            rows = slice(gap.start, gap.end + 1)
            fraction = (frames[rows] - frames[before]) / (frames[after] - frames[before])
            xs[rows] = xs[before] + (xs[after] - xs[before]) * fraction
            ys[rows] = ys[before] + (ys[after] - ys[before]) * fraction
            interpolated[rows] = True
        x[point], y[point] = xs, ys
    return replace(pose, x_px=x, y_px=y), interpolated


# --- Sinalização de lacunas longas (SCRUM-129) -------------------------------


@dataclass(frozen=True)
class FlaggedSegment:
    """Trecho sinalizado para revisão humana (RN02/RN04).

    Attributes:
        start_frame: Primeiro quadro do trecho (índice no vídeo).
        end_frame: Último quadro do trecho, inclusive.
        missing_points: Pontos que faltam em alguma parte do trecho.
        pending: True se o trecho ainda não foi inteiramente revisado.
    """

    start_frame: int
    end_frame: int
    missing_points: tuple[str, ...]
    pending: bool = True

    @property
    def length(self) -> int:
        """Quantidade de quadros do trecho."""
        return self.end_frame - self.start_frame + 1

    def as_record(self) -> dict[str, Any]:
        """O trecho em JSON, como fica no relatório e nos metadados."""
        return {
            "inicio": self.start_frame,
            "fim": self.end_frame,
            "pontos": list(self.missing_points),
            "pendente": self.pending,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> FlaggedSegment:
        """Inverso de `as_record`."""
        return cls(
            int(record["inicio"]),
            int(record["fim"]),
            tuple(record["pontos"]),
            bool(record["pendente"]),
        )


def flag_long_gaps(
    pose: PoseFrames,
    max_frames: int,
    reviewed_ranges: Iterable[tuple[int, int]] = (),
) -> list[FlaggedSegment]:
    """Sinaliza, sem interpolar, as lacunas longas e as de borda (RN02).

    As lacunas de todos os pontos são unidas em trechos de quadros contíguos,
    para que a revisão visite cada trecho uma vez só, com a lista dos pontos
    que faltam nele.

    Args:
        pose: Pose em pixels (normalmente já interpolada).
        max_frames: Limite de lacuna curta; acima dele a lacuna é longa.
        reviewed_ranges: Intervalos de quadros (início, fim, inclusive) já
            revisados. Um trecho inteiramente dentro deles não fica pendente.

    Returns:
        Os trechos, em ordem de quadro.
    """
    rows = len(pose.frames)
    flagged_by_point = {point: np.zeros(rows, dtype=bool) for point in KEYPOINTS}
    for point in KEYPOINTS:
        for gap in find_gaps(_valid(pose, point)):
            if gap.at_edge or gap.length > max_frames:
                flagged_by_point[point][gap.start : gap.end + 1] = True
    flagged = np.logical_or.reduce(list(flagged_by_point.values()))

    reviewed = np.zeros(rows, dtype=bool)
    for start, end in reviewed_ranges:
        reviewed |= (pose.frames >= start) & (pose.frames <= end)

    segments = []
    for start, end in _present_runs(flagged):
        missing = tuple(p for p in KEYPOINTS if flagged_by_point[p][start:end].any())
        segments.append(
            FlaggedSegment(
                int(pose.frames[start]),
                int(pose.frames[end - 1]),
                missing,
                pending=not bool(reviewed[start:end].all()),
            )
        )
    return segments


# --- Cobertura (SCRUM-130) ---------------------------------------------------


def pose_coverage(pose: PoseFrames) -> float:
    """Fração dos quadros com os três pontos com coordenada (RN03).

    Quadro interpolado ou corrigido conta, porque tem coordenada. Para a
    cobertura só da detecção, chame com a pose bruta.

    Raises:
        ValueError: Se a pose não tiver nenhum quadro.
    """
    if len(pose.frames) == 0:
        raise ValueError("Pose sem nenhum quadro: cobertura indefinida.")
    complete = np.logical_and.reduce([_valid(pose, point) for point in KEYPOINTS])
    return float(complete.mean())


def classify(coverage: float, minimum: float, pending_segments: int) -> PoseQuality:
    """Qualidade do trial (RN06).

    Trecho sinalizado ainda não revisado deixa a revisão pendente, porque a
    revisão pode recuperar a cobertura. Sem pendência, cobertura abaixo do mínimo
    é qualidade insuficiente "mesmo após revisão".
    """
    if pending_segments > 0:
        return PoseQuality.REVISAO_PENDENTE
    if coverage < minimum:
        return PoseQuality.INSUFICIENTE
    return PoseQuality.SUFICIENTE


# --- Correções manuais (SCRUM-132) -------------------------------------------


@dataclass(frozen=True)
class PointCorrection:
    """Posição de um ponto marcada à mão pelo operador num quadro (RN05).

    Attributes:
        frame: Índice do quadro no vídeo original.
        point: Um de `KEYPOINTS`.
        x_px, y_px: Posição em pixels do quadro original (eixos da imagem).
    """

    frame: int
    point: str
    x_px: float
    y_px: float

    def __post_init__(self) -> None:
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("O quadro da correção deve ser um inteiro maior ou igual a zero.")
        if self.point not in KEYPOINTS:
            raise ValueError(f"Ponto inválido na correção: {self.point!r}.")
        for value in (self.x_px, self.y_px):
            if isinstance(value, bool) or not np.isfinite(value) or value < 0:
                raise ValueError("A posição corrigida deve ser finita e não negativa (pixels).")


def apply_corrections(
    pose: PoseFrames, corrections: Iterable[PointCorrection]
) -> tuple[PoseFrames, np.ndarray]:
    """Sobrepõe as correções manuais à pose; a última de cada quadro e ponto vence.

    O ponto corrigido perde a confiança do modelo (NaN): a posição não é mais
    a que o modelo previu.

    Returns:
        A pose corrigida e a máscara das linhas com alguma correção.

    Raises:
        ValueError: Se alguma correção estiver fora dos quadros da série.
    """
    row_of = {int(frame): row for row, frame in enumerate(pose.frames)}
    x = {p: pose.x_px[p].astype(np.float64) for p in KEYPOINTS}
    y = {p: pose.y_px[p].astype(np.float64) for p in KEYPOINTS}
    confidence = {p: pose.confidence[p].astype(np.float64) for p in KEYPOINTS}
    corrected = np.zeros(len(pose.frames), dtype=bool)
    for correction in corrections:
        row = row_of.get(correction.frame)
        if row is None:
            raise ValueError(
                f"Correção no quadro {correction.frame}, fora da série "
                f"({int(pose.frames[0])}..{int(pose.frames[-1])})."
            )
        x[correction.point][row] = correction.x_px
        y[correction.point][row] = correction.y_px
        confidence[correction.point][row] = np.nan
        corrected[row] = True
    return replace(pose, x_px=x, y_px=y, confidence=confidence), corrected


# --- Composição (SCRUM-127) --------------------------------------------------


@dataclass(frozen=True)
class PostProcessed:
    """Resultado de `postprocess_pose`.

    Attributes:
        pose: Pose tratada, em pixels, pronta para `build_series`.
        interpolated: Linhas com algum ponto interpolado (coluna `interpolado`).
        corrected: Linhas com alguma correção manual aplicada.
        segments: Trechos sinalizados para revisão.
        report: Relatório de qualidade em JSON (execução, metadados da série).
    """

    pose: PoseFrames
    interpolated: np.ndarray
    corrected: np.ndarray
    segments: tuple[FlaggedSegment, ...]
    report: dict[str, Any]

    @property
    def quality(self) -> PoseQuality:
        """Qualidade classificada (RN06)."""
        return PoseQuality(self.report["qualidade"])

    @property
    def pending(self) -> tuple[FlaggedSegment, ...]:
        """Trechos ainda não revisados."""
        return tuple(segment for segment in self.segments if segment.pending)


def postprocess_pose(
    pose: PoseFrames,
    params: QualityParams,
    *,
    corrections: Sequence[PointCorrection] = (),
    reviewed_ranges: Iterable[tuple[int, int]] = (),
    fps_variable: bool = False,
) -> PostProcessed:
    """Correções → suavização → interpolação → sinalização → cobertura (US-10).

    É uma função pura da pose bruta, das correções e dos parâmetros: rodar de
    novo com as mesmas entradas dá o mesmo resultado, e a pose nunca é suavizada
    duas vezes. Correções fora dos quadros da série (por exemplo, depois de um
    novo recorte do intervalo útil) são ignoradas e contadas no relatório.

    Args:
        pose: Pose bruta da inferência, em pixels (`read_pose_csv`).
        params: Parâmetros de `load_quality_params`.
        corrections: Correções manuais, em ordem de registro (a última vence).
        reviewed_ranges: Intervalos de quadros já revisados (`pose review`).
        fps_variable: `trials.fps_is_variable` — gera a ressalva do RN07 se
            houver interpolação.

    Raises:
        ValueError: Se a pose não tiver quadros.
    """
    detection_coverage = pose_coverage(pose)
    first, last = int(pose.frames[0]), int(pose.frames[-1])
    inside = [c for c in corrections if first <= c.frame <= last]
    corrected_pose, corrected = apply_corrections(pose, inside)
    smoothed = smooth_points(corrected_pose, params.smoothing_window)
    filled, interpolated = interpolate_short_gaps(smoothed, params.short_gap_max_frames)
    segments = tuple(flag_long_gaps(filled, params.short_gap_max_frames, reviewed_ranges))
    coverage = pose_coverage(filled)
    pending = sum(segment.pending for segment in segments)
    quality = classify(coverage, params.min_coverage, pending)
    rows = len(pose.frames)
    report = {
        "cobertura": coverage,
        "cobertura_deteccao": detection_coverage,
        "cobertura_minima": params.min_coverage,
        "qualidade": quality.value,
        "quadros": rows,
        "quadros_interpolados": int(interpolated.sum()),
        "fracao_interpolada": float(interpolated.mean()),
        "quadros_corrigidos": int(corrected.sum()),
        "correcoes_ignoradas": len(corrections) - len(inside),
        "trechos_sinalizados": [segment.as_record() for segment in segments],
        "trechos_pendentes": pending,
        "parametros": params.as_record(),
        "ressalva_fps_variavel": (
            FPS_VARIABLE_CAVEAT if fps_variable and interpolated.any() else None
        ),
    }
    return PostProcessed(filled, interpolated, corrected, segments, report)


def segments_from_report(report: Mapping[str, Any]) -> list[FlaggedSegment]:
    """Trechos sinalizados gravados num relatório (`pos_processamento` da série)."""
    return [FlaggedSegment.from_record(item) for item in report.get("trechos_sinalizados", [])]
