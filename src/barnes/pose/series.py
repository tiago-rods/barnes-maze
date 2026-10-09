"""Série temporal de posição e orientação da cabeça a partir da pose inferida (US-09).

Funções puras, sem banco nem GPU: recebem a pose bruta em pixels (o `pose.csv`
de `barnes.pose.inference.infer_trial`), a escala da montagem (US-02) e o
intervalo útil (US-03), e montam a tabela do contrato em
`barnes.pose.trajectory`. A orquestração (ler o banco, registrar a execução,
gravar o arquivo) fica na CLI.

Convenção angular (US-04, `docs/definicoes-metricas.md` §6.5): eixos da imagem,
y para baixo; θ = 0° aponta para +x e cresce no sentido horário na tela.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa

from barnes.io.trim import TrialInterval
from barnes.pose.annotations import KEYPOINTS
from barnes.pose.trajectory import (
    ANGLE_CONVENTION,
    CONTRACT_VERSION,
    SCHEMA,
    validate_trajectory,
    with_metadata,
)

# Cabeçalho de `pose.csv` escrito por `barnes.pose.inference.infer_trial`.
POSE_CSV_COLUMNS = (
    "trial",
    "quadro",
    "time_s",
    *[
        f"{point}_{suffix}"
        for point in KEYPOINTS
        for suffix in ("x_image", "y_image", "confidence")
    ],
)


class SeriesError(ValueError):
    """Pose inferida incompatível com o trial (quadros faltando, formato, escala)."""


@dataclass(frozen=True)
class PoseFrames:
    """Pose bruta por quadro, em pixels, como saiu da inferência.

    Attributes:
        frames: Índice de cada quadro no vídeo, na ordem do arquivo.
        x_px, y_px, confidence: Por ponto (`KEYPOINTS`), um array por quadro;
            NaN onde o modelo não detectou o ponto.
    """

    frames: np.ndarray
    x_px: dict[str, np.ndarray]
    y_px: dict[str, np.ndarray]
    confidence: dict[str, np.ndarray]


def _number(text: str, *, line: int, column: str) -> float:
    if text == "":
        return math.nan
    try:
        value = float(text)
    except ValueError as exc:
        raise SeriesError(f"Valor inválido em pose.csv, linha {line}, coluna {column}.") from exc
    return value if math.isfinite(value) else math.nan


def read_pose_csv(path: str | Path) -> PoseFrames:
    """Lê o `pose.csv` da inferência (US-07/08) sem alterar nenhum valor.

    Célula vazia é ponto ausente e vira NaN — nunca 0 nem o valor anterior.

    Raises:
        SeriesError: Cabeçalho diferente do da inferência, ou valor ilegível.
    """
    with Path(path).open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != POSE_CSV_COLUMNS:
            raise SeriesError(
                f"Cabeçalho de {path} não é o de `pose infer`: esperado {', '.join(POSE_CSV_COLUMNS)}."
            )
        frames: list[int] = []
        values: dict[str, list[float]] = {
            f"{point}_{suffix}": []
            for point in KEYPOINTS
            for suffix in ("x_image", "y_image", "confidence")
        }
        for row in reader:
            try:
                frames.append(int(row["quadro"]))
            except ValueError as exc:
                raise SeriesError(f"Quadro inválido em {path}, linha {reader.line_num}.") from exc
            for column, bucket in values.items():
                bucket.append(_number(row[column], line=reader.line_num, column=column))
    as_array = {key: np.asarray(items, dtype=np.float64) for key, items in values.items()}
    return PoseFrames(
        frames=np.asarray(frames, dtype=np.int64),
        x_px={p: as_array[f"{p}_x_image"] for p in KEYPOINTS},
        y_px={p: as_array[f"{p}_y_image"] for p in KEYPOINTS},
        confidence={p: as_array[f"{p}_confidence"] for p in KEYPOINTS},
    )


def px_to_cm(values_px: np.ndarray, cm_per_px: float) -> np.ndarray:
    """Converte coordenadas em pixel para cm com a escala da montagem (SCRUM-117).

    Usa um único fator para os dois eixos, como a calibração da US-02. NaN
    (ponto ausente) continua NaN.

    Args:
        values_px: Coordenadas em pixel, de qualquer formato.
        cm_per_px: Escala da montagem (`StoredCalibration.cm_per_px`).

    Returns:
        As mesmas coordenadas em cm, como float64.

    Raises:
        ValueError: Se a escala não for um número finito positivo.
    """
    if (
        isinstance(cm_per_px, bool)
        or not isinstance(cm_per_px, int | float)
        or not np.isfinite(cm_per_px)
        or cm_per_px <= 0
    ):
        raise ValueError("A escala cm_per_px deve ser um número finito e positivo.")
    return np.asarray(values_px, dtype=np.float64) * float(cm_per_px)


def head_angle_deg(
    center_x: np.ndarray, center_y: np.ndarray, snout_x: np.ndarray, snout_y: np.ndarray
) -> np.ndarray:
    """Orientação da cabeça pelo eixo centro do corpo → focinho, em graus (SCRUM-119).

    Nos eixos da imagem (y para baixo), `atan2(dy, dx)` dá 0° para +x e ângulos
    crescendo no sentido horário na tela — a convenção de `holes.angle_deg`.
    O resultado fica em [0, 360). É NaN quando falta algum dos dois pontos ou
    quando eles coincidem (direção indefinida); nunca herda o quadro anterior.

    Args:
        center_x, center_y: Centro do corpo (qualquer unidade; a mesma nos dois).
        snout_x, snout_y: Focinho.

    Returns:
        θ em graus, mesmo formato das entradas.
    """
    dx = np.asarray(snout_x, dtype=np.float64) - np.asarray(center_x, dtype=np.float64)
    dy = np.asarray(snout_y, dtype=np.float64) - np.asarray(center_y, dtype=np.float64)
    theta = np.degrees(np.arctan2(dy, dx)) % 360.0
    # % 360 de um negativo minúsculo pode dar exatamente 360.0.
    theta = np.where(theta >= 360.0, 0.0, theta)
    defined = np.isfinite(dx) & np.isfinite(dy) & ((dx != 0) | (dy != 0))
    return np.where(defined, theta, np.nan)


def build_series(
    pose: PoseFrames,
    *,
    trial_id: int,
    execucao_id: int,
    expected_frames: tuple[int, int],
    fps: float,
    interval: TrialInterval,
    fps_variable: bool,
    cm_per_px: float,
    content_hash: str,
    model_id: str,
    generated_at: datetime | None = None,
) -> pa.Table:
    """Monta a série (x, y, θ, t) do trial no contrato de `barnes.pose.trajectory`.

    - Uma linha por quadro de `expected_frames` (os quadros que a inferência
      processou no intervalo útil); quadro faltando ou repetido é erro, não
      lacuna silenciosa.
    - Ponto não detectado fica NaN com `*_valido = false`; quadro sem focinho ou
      sem centro do corpo tem `pose_valida = false` e θ NaN — sem repetir o
      quadro anterior (SCRUM-121). O preenchimento é da US-10.
    - `t_s` = quadro / fps − início do intervalo útil (US-03 RN05). Com fps
      variável (US-01), `t_s` é aproximado: `fps_variavel` vai em toda linha e
      nos metadados (SCRUM-118).

    Args:
        pose: Pose bruta lida por `read_pose_csv`.
        trial_id: `trials.id`.
        execucao_id: Execução (US-27) que gera esta série.
        expected_frames: (primeiro, último) quadro processados pela inferência,
            inclusive (`processed_interval_frames` do registro).
        fps: fps medido do vídeo (`trials.fps_real`) — a base de `t_s`.
        interval: Intervalo útil do trial.
        fps_variable: `trials.fps_is_variable`.
        cm_per_px: Escala da montagem (US-02).
        content_hash: Hash do vídeo (US-01), para os metadados.
        model_id: Modelo de pose usado (US-07), para os metadados.
        generated_at: Instante de geração (padrão: agora, UTC).

    Returns:
        A tabela, já validada contra o contrato e com os metadados.

    Raises:
        SeriesError: Se os quadros da pose não forem exatamente os esperados,
            ou se fps/escala forem inválidos.
    """
    if (
        isinstance(fps, bool)
        or not isinstance(fps, int | float)
        or not fps > 0
        or not math.isfinite(fps)
    ):
        raise SeriesError("fps deve ser um número finito e positivo (trials.fps_real).")
    first, last = expected_frames
    expected = np.arange(first, last + 1)
    if pose.frames.shape != expected.shape or not (pose.frames == expected).all():
        missing = sorted(set(expected.tolist()) - set(pose.frames.tolist()))
        detail = (
            f"faltam os quadros {missing[:10]}" if missing else "quadros fora de ordem ou repetidos"
        )
        raise SeriesError(
            f"A pose não cobre os quadros {first}..{last} do intervalo útil: {detail}. "
            "Refaça a inferência do trial."
        )
    try:
        x_cm = {p: px_to_cm(pose.x_px[p], cm_per_px) for p in KEYPOINTS}
        y_cm = {p: px_to_cm(pose.y_px[p], cm_per_px) for p in KEYPOINTS}
    except ValueError as exc:
        raise SeriesError(str(exc)) from exc
    valid = {p: np.isfinite(x_cm[p]) & np.isfinite(y_cm[p]) for p in KEYPOINTS}
    theta = head_angle_deg(
        x_cm["centro_corpo"], y_cm["centro_corpo"], x_cm["focinho"], y_cm["focinho"]
    )
    rows = len(expected)
    columns: dict[str, Any] = {
        "trial_id": np.full(rows, trial_id, dtype=np.int32),
        "execucao_id": np.full(rows, execucao_id, dtype=np.int32),
        "quadro": expected.astype(np.int32),
        "t_s": expected / float(fps) - interval.start_s,
    }
    for point in KEYPOINTS:
        # Coordenada de ponto inválido é NaN nos dois eixos (nunca meio ponto).
        columns[f"{point}_x_cm_image"] = np.where(valid[point], x_cm[point], np.nan)
        columns[f"{point}_y_cm_image"] = np.where(valid[point], y_cm[point], np.nan)
    for point in KEYPOINTS:
        columns[f"{point}_confianca"] = pose.confidence[point]
    for point in KEYPOINTS:
        columns[f"{point}_valido"] = valid[point]
    columns["pose_valida"] = np.isfinite(theta)
    columns["theta_deg_image"] = theta
    columns["interpolado"] = np.zeros(rows, dtype=bool)
    columns["fps_variavel"] = np.full(rows, bool(fps_variable))

    table = with_metadata(
        pa.table(columns, schema=SCHEMA),
        {
            "contrato_versao": CONTRACT_VERSION,
            "trial_id": trial_id,
            "execucao_id": execucao_id,
            "content_hash": content_hash,
            "model_id": model_id,
            "fps_real": float(fps),
            "fps_variavel": bool(fps_variable),
            "cm_per_px": float(cm_per_px),
            "px_per_10cm": 10 / float(cm_per_px),
            "intervalo_inicio_s": float(interval.start_s),
            "intervalo_fim_s": float(interval.end_s),
            "convencao_angular": ANGLE_CONVENTION,
            "gerado_em": (generated_at or datetime.now(UTC)).isoformat(),
        },
    )
    validate_trajectory(table)
    return table
