"""Persistência da escala px→cm por montagem no banco de dados (US-02).

A escala mora em `maze_configs` (colunas `px_per_10cm`, `calibration_date`,
`measured_error_pct` — já reservadas pela 0001) em vez de uma tabela própria:
RN05 fala da "escala da montagem", não de uma identidade separada de câmera.
Recalibrar sobrescreve essas colunas (RN05); não há histórico de versões —
quem precisa saber se um resultado ficou obsoleto compara
`trial_results.calculated_at`/`px_per_10cm_used` contra os valores atuais
aqui (ver `barnes.db.trial_results`).

`barnes.io.calibration` calcula em cm/px (natural para a matemática dos
segmentos); aqui converte-se para px_per_10cm na escrita e de volta para
cm/px na leitura — ponto único de conversão, para não espalhar `10 / x` por
várias partes do código.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

import psycopg

from barnes.io.calibration import CalibrationResult, Segment


class CalibrationRequiredError(ValueError):
    """A montagem não tem escala calibrada ainda."""


@dataclass(frozen=True)
class StoredCalibration:
    cm_per_px: float
    calibration_date: date
    measured_error_pct: float | None
    segments: tuple[Segment, Segment]
    reference_video: str | None
    reference_frame: int | None
    reference_width: int | None
    reference_height: int | None


def _segments_json(segments: tuple[Segment, Segment]) -> str:
    return json.dumps(
        [{"start": s.start, "end": s.end, "length_cm": s.length_cm} for s in segments]
    )


def _segments_from_json(raw: str | None) -> tuple[Segment, Segment]:
    if raw is None:
        raise ValueError("Dado de calibração incompleto: segmentos não encontrados.")
    first, second = json.loads(raw)
    return (
        Segment(tuple(first["start"]), tuple(first["end"]), first["length_cm"]),
        Segment(tuple(second["start"]), tuple(second["end"]), second["length_cm"]),
    )


def save_calibration(
    conn: psycopg.Connection,
    maze_config_id: int,
    result: CalibrationResult,
    *,
    reference_video: str,
    reference_frame: int,
    reference_size: tuple[int, int],
) -> None:
    """Grava a escala calculada na montagem (RN01/RN02/RN05).

    Não comita a transação. Trava a linha de `maze_configs` (`FOR UPDATE`)
    para serializar com uma publicação de métricas em andamento na mesma
    montagem (ver `barnes.db.trial_results.upsert_trial_result`). Uma nova
    calibração zera `measured_error_pct`: a verificação independente (RN04)
    precisa ser refeita contra a escala nova.

    Args:
        conn: Conexão psycopg aberta.
        maze_config_id: Id da `maze_configs` a calibrar.
        result: Resultado de `barnes.io.calibration.calculate_calibration`.
        reference_video: Caminho do vídeo usado como referência.
        reference_frame: Índice do quadro usado como referência.
        reference_size: Resolução (largura, altura) do quadro de referência.

    Raises:
        ValueError: Se a montagem não existir.
    """
    width, height = reference_size
    px_per_10cm = 10 / result.cm_per_px
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM maze_configs WHERE id = %s FOR UPDATE", (maze_config_id,))
        if cur.fetchone() is None:
            raise ValueError(f"maze_config {maze_config_id} não encontrada.")
        cur.execute(
            """
            UPDATE maze_configs
            SET px_per_10cm = %s,
                calibration_date = CURRENT_DATE,
                measured_error_pct = NULL,
                calibration_segments = %s,
                calibration_reference_video = %s,
                calibration_reference_frame = %s,
                calibration_width_px = %s,
                calibration_height_px = %s
            WHERE id = %s
            """,
            (
                px_per_10cm,
                _segments_json(result.segments),
                reference_video,
                reference_frame,
                width,
                height,
                maze_config_id,
            ),
        )


def save_verification(conn: psycopg.Connection, maze_config_id: int, relative_error: float) -> None:
    """Grava o erro medido contra uma distância independente (RN04).

    Não comita a transação.

    Args:
        conn: Conexão psycopg aberta.
        maze_config_id: Id da `maze_configs` verificada.
        relative_error: Erro relativo retornado por
            `barnes.io.calibration.verify_distance` (fração, ex. 0.02 = 2%).

    Raises:
        ValueError: Se a montagem não existir.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE maze_configs SET measured_error_pct = %s WHERE id = %s RETURNING id",
            (relative_error * 100, maze_config_id),
        )
        if cur.fetchone() is None:
            raise ValueError(f"maze_config {maze_config_id} não encontrada.")


def get_calibration(conn: psycopg.Connection, maze_config_id: int) -> StoredCalibration | None:
    """Lê a escala atual da montagem, sem exigir que já exista (US-02 RN02).

    Args:
        conn: Conexão psycopg aberta.
        maze_config_id: Id da `maze_configs` a consultar.

    Returns:
        A escala atual, ou `None` se a montagem ainda não foi calibrada.

    Raises:
        ValueError: Se a montagem não existir.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT px_per_10cm, calibration_date, measured_error_pct, calibration_segments,
                   calibration_reference_video, calibration_reference_frame,
                   calibration_width_px, calibration_height_px
            FROM maze_configs WHERE id = %s
            """,
            (maze_config_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"maze_config {maze_config_id} não encontrada.")
    px_per_10cm, calibration_date, measured_error_pct, segments_json, video, frame, width, height = row
    if px_per_10cm is None:
        return None
    return StoredCalibration(
        cm_per_px=10 / px_per_10cm,
        calibration_date=calibration_date,
        measured_error_pct=measured_error_pct,
        segments=_segments_from_json(segments_json),
        reference_video=video,
        reference_frame=frame,
        reference_width=width,
        reference_height=height,
    )


def require_calibration(conn: psycopg.Connection, maze_config_id: int) -> StoredCalibration:
    """Como `get_calibration`, mas exige que a escala já exista (RN03).

    Raises:
        ValueError: Se a montagem não existir.
        CalibrationRequiredError: Se a montagem existir mas não tiver escala.
    """
    calibration = get_calibration(conn, maze_config_id)
    if calibration is None:
        raise CalibrationRequiredError(
            f"A montagem {maze_config_id} exige calibração antes do cálculo de "
            "distância, velocidade ou eficiência de rota."
        )
    return calibration


def validate_frame_size(calibration: StoredCalibration, frame_size: tuple[int, int]) -> None:
    """Confere se um quadro usa a mesma resolução da calibração (RN02).

    Raises:
        ValueError: Se a resolução for diferente da usada na calibração.
    """
    reference = (calibration.reference_width, calibration.reference_height)
    if tuple(frame_size) != reference:
        raise ValueError(
            f"Resolução {frame_size} diferente da calibração {reference}. "
            "Use as coordenadas originais e calibre esta montagem novamente para esta resolução."
        )
