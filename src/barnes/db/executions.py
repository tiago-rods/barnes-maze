"""Registro de execuções de processamento de trials em `execucao` (US-27 RN01).

Complementa `barnes.db.pose_executions` (treino, avaliação e inferência da
US-07/US-08): aqui fica o `kind = 'processamento'` — todo cálculo que gera
métricas ou eventos de um trial. Cada processamento grava, em colunas
consultáveis, o que é preciso para reproduzi-lo meses depois (Cenário 2):
modelo de pose (se houver), limiares vigentes, parâmetros, commit e estado
sujo do repositório, hash do vídeo e horários. Como toda linha de
`execucao`, é imutável: reprocessar cria outra execução.

Não comita a transação — quem chama grava a execução e as métricas que
dependem dela na mesma transação, para nunca sobrar execução sem resultado
nem resultado sem execução.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from barnes.db.pose_executions import StoredExecution, get_execution, list_executions
from barnes.provenance import GitState, ThresholdsSnapshot

__all__ = [
    "StoredExecution",
    "get_execution",
    "list_executions",
    "record_processing_execution",
]


def record_processing_execution(
    conn: psycopg.Connection,
    *,
    trial_id: int,
    maze_config_id: int,
    parameters: dict[str, Any],
    thresholds: ThresholdsSnapshot,
    git: GitState,
    video_hash: str,
    started_at: datetime,
    model_id: str | None = None,
    duration_seconds: float | None = None,
    artifact_path: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Acrescenta uma execução de processamento e devolve seu id (RN01/RN05).

    Args:
        conn: Conexão psycopg aberta.
        trial_id: Trial processado.
        maze_config_id: Montagem do trial — a FK composta da 0006 recusa
            uma montagem que não seja a do trial.
        parameters: Parâmetros da chamada (arquivos de entrada, opções,
            escala usada), em JSON.
        thresholds: Limiares de `configs/default.yaml` vigentes.
        git: Commit e estado sujo do código executado (`git_revision_record`).
        video_hash: Hash do vídeo efetivamente verificado neste processamento.
        started_at: Início do processamento.
        model_id: Modelo de pose usado, quando o processamento parte de uma
            inferência (US-09 em diante); `None` para trajetória já extraída.
        duration_seconds: Duração do processamento, se medida.
        artifact_path: Arquivo gerado (ex.: o Parquet da trajetória, US-09).
        metadata: Informações extras (ex.: o registro de `git_revision_record`).

    Returns:
        O id da nova linha em `execucao`.

    Raises:
        ValueError: Se parâmetros ou metadados não forem JSON finito.
        psycopg.errors.ForeignKeyViolation: Trial ou montagem inexistente,
            ou trial de outra montagem.
    """
    record = dict(metadata or {})
    record.setdefault("run_id", f"processamento-{uuid.uuid4().hex}")
    for name, value in (("parameters", parameters), ("metadata", record)):
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} deve conter apenas valores JSON finitos.") from exc
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO execucao (
                kind, model_id, maze_config_id, trial_id, status, duration_seconds,
                artifact_path, metadata, git_commit, git_dirty, limiares, limiares_sha256,
                parametros, video_hash, iniciado_em
            ) VALUES (
                'processamento', %s, %s, %s, 'concluido', %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING id
            """,
            (
                model_id,
                maze_config_id,
                trial_id,
                duration_seconds,
                artifact_path,
                Jsonb(record),
                git.commit,
                git.dirty,
                Jsonb(thresholds.values),
                thresholds.sha256,
                Jsonb(parameters),
                video_hash,
                started_at,
            ),
        )
        return cur.fetchone()[0]
