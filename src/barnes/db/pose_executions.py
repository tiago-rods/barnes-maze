"""Auditoria de execuções de pose (US-07/US-08), sem controle de transação.

O manifesto completo fica em ``metadata``: versão e hashes dos dados,
hiperparâmetros, ambiente, máquina, commit, horários e hashes dos artefatos.
Os pesos são arquivos locais, identificados por ``model_id``; não são blobs
no banco. Uma nova tentativa gera outra linha, inclusive após falha.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import psycopg
from psycopg.types.json import Jsonb

from barnes.io.trim import TrialInterval, interval_from_seconds

ExecutionKind = Literal["treino", "avaliacao", "inferencia"]
ExecutionStatus = Literal["concluido", "falhou"]
_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_COLUMNS = (
    "id, kind, model_id, maze_config_id, trial_id, status, "
    "duration_seconds, artifact_path, metadata, recorded_at"
)


@dataclass(frozen=True)
class StoredExecution:
    """Tentativa terminada e seu manifesto de proveniência."""

    id: int
    kind: ExecutionKind
    model_id: str
    maze_config_id: int
    trial_id: int | None
    status: ExecutionStatus
    duration_seconds: float | None
    artifact_path: str | None
    metadata: dict[str, Any]
    recorded_at: datetime


@dataclass(frozen=True)
class StoredInferenceTrial:
    """Identidade e recorte do vídeo registrado para inferência local."""

    id: int
    maze_config_id: int
    filepath: Path
    content_hash: str
    fps_real: float
    frame_count: int
    width_px: int
    height_px: int
    interval: TrialInterval | None


def get_inference_trial(conn: psycopg.Connection, trial_id: int) -> StoredInferenceTrial:
    """Lê o contexto registrado do trial, sem acessar ou aceitar outro vídeo.

    A CLI deve conferir o hash do arquivo antes de inferir: mover/renomear um
    vídeo preserva sua identidade, substituir o conteúdo não. Um trial sem
    recorte retorna ``interval=None``; cabe à inferência recusar sua execução
    até a resolução explícita do intervalo útil (US-03).

    Raises:
        ValueError: Se o trial não existir.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT maze_config_id, filepath, content_hash, fps_real, frame_count,
                   width_px, height_px, start_time_seconds, end_time_seconds,
                   interval_manually_adjusted
            FROM trials WHERE id = %s
            """,
            (trial_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"Trial {trial_id} não encontrado.")
    maze_id, filepath, content_hash, fps, frames, width, height, start, end, manual = row
    interval = (
        None if start is None or end is None
        else interval_from_seconds(start, end, fps, manually_adjusted=manual)
    )
    return StoredInferenceTrial(
        trial_id, maze_id, Path(filepath), content_hash, fps, frames, width, height, interval,
    )


def record_execution(
    conn: psycopg.Connection,
    *,
    kind: ExecutionKind,
    model_id: str,
    maze_config_id: int,
    metadata: dict[str, Any],
    trial_id: int | None = None,
    status: ExecutionStatus = "concluido",
    duration_seconds: float | None = None,
    artifact_path: str | None = None,
) -> int:
    """Acrescenta uma execução à tabela ``execucao`` e devolve seu id.

    Não comita a transação. O chamador registra o manifesto completo nos
    metadados e controla a persistência junto às demais operações da CLI.
    Com ``metadata.run_id`` estável, repetir uma gravação idêntica devolve o
    id anterior; reutilizar o identificador com outra proveniência é recusado.
    Treino pertence à montagem; inferência sempre pertence a um trial da
    mesma montagem, verificado por chave estrangeira composta no banco.

    Raises:
        ValueError: Se os campos não descrevem uma tentativa válida.
        TypeError: Se metadata não for um dicionário.
        psycopg.errors.ForeignKeyViolation: Se a montagem/trial não existir
            ou se o trial pertencer a outra montagem.
    """
    if kind not in ("treino", "avaliacao", "inferencia"):
        raise ValueError("Tipo de execução inválido: use treino, avaliacao ou inferencia.")
    if status not in ("concluido", "falhou"):
        raise ValueError("Status inválido: use concluido ou falhou.")
    if not isinstance(model_id, str) or not _MODEL_ID.fullmatch(model_id):
        raise ValueError("model_id deve ter 1 a 128 caracteres: letras, números, ponto, _ ou -.")
    if kind == "treino" and trial_id is not None:
        raise ValueError("Treino é registrado por montagem, sem trial_id.")
    if kind == "inferencia" and trial_id is None:
        raise ValueError("Inferência exige trial_id.")
    if duration_seconds is not None and (
        isinstance(duration_seconds, bool)
        or not isinstance(duration_seconds, (int, float))
        or not math.isfinite(duration_seconds)
        or duration_seconds < 0
    ):
        raise ValueError("duration_seconds deve ser finito e maior ou igual a zero.")
    if artifact_path is not None and (
        not isinstance(artifact_path, str) or not artifact_path.strip()
    ):
        raise ValueError("artifact_path não pode ser vazio.")
    if kind == "inferencia" and status == "concluido" and (
        duration_seconds is None or artifact_path is None
    ):
        raise ValueError("Inferência concluída exige duração e caminho do artefato.")
    if not isinstance(metadata, dict):
        raise TypeError("metadata deve ser um objeto JSON com o manifesto da execução.")
    run_id = metadata.get("run_id")
    if "run_id" in metadata and (
        not isinstance(run_id, str) or not 1 <= len(run_id.strip()) <= 256
    ):
        raise ValueError("metadata.run_id deve ser texto não vazio com até 256 caracteres.")
    try:
        json.dumps(metadata, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("metadata deve conter apenas valores JSON finitos.") from exc

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO execucao (
                kind, model_id, maze_config_id, trial_id, status,
                duration_seconds, artifact_path, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (kind, (metadata ->> 'run_id')) WHERE metadata ? 'run_id'
                DO NOTHING
            RETURNING id
            """,
            (
                kind, model_id, maze_config_id, trial_id, status,
                duration_seconds, artifact_path, Jsonb(metadata),
            ),
        )
        inserted = cur.fetchone()
        if inserted is not None:
            return inserted[0]
        cur.execute(
            """
            SELECT id, kind, model_id, maze_config_id, trial_id, status,
                   duration_seconds, artifact_path, metadata
            FROM execucao WHERE kind = %s AND metadata ->> 'run_id' = %s
            """,
            (kind, run_id),
        )
        existing = cur.fetchone()
        expected = (
            kind, model_id, maze_config_id, trial_id, status,
            duration_seconds, artifact_path, metadata,
        )
        if existing is None or tuple(existing[1:]) != expected:
            raise ValueError("run_id já registrado com outra proveniência; preserve o registro original.")
        return existing[0]


def get_execution(conn: psycopg.Connection, execution_id: int) -> StoredExecution:
    """Lê o registro integral de uma execução; não comita a transação."""
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM execucao WHERE id = %s", (execution_id,))
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"Execução {execution_id} não encontrada.")
    return StoredExecution(*row)


def list_executions(
    conn: psycopg.Connection,
    *,
    trial_id: int | None = None,
    model_id: str | None = None,
) -> list[StoredExecution]:
    """Lista tentativas em ordem de registro, com filtros opcionais."""
    conditions = []
    values: list[int | str] = []
    if trial_id is not None:
        conditions.append("trial_id = %s")
        values.append(trial_id)
    if model_id is not None:
        conditions.append("model_id = %s")
        values.append(model_id)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    with conn.cursor() as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM execucao{where} ORDER BY id", values)
        return [StoredExecution(*row) for row in cur.fetchall()]
