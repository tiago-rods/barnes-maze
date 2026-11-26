"""Auditoria permanente dos jobs em segundo plano do wizard web (RQ + Redis).

O RQ já guarda status/resultado de cada job no Redis, mas com TTL — some
depois de um tempo e não há outro usuário consultando. Esta tabela
(`jobs`, migração `0013`) é o registro que sobrevive a isso: cada submissão
rastreável no dashboard, sucesso ou falha, independente do Redis.

Não é o mesmo registro que `barnes.db.executions`/`pose_executions`
(`execucao`, US-27): `execucao` é a prova imutável de um processamento bem
sucedido; `jobs` é o rastro efêmero do lado web de "o que foi submetido e o
que aconteceu com isso" — inclusive as tentativas que falharam antes de
gerar qualquer `execucao`.

Não comita a transação — quem chama decide quando persistir, no mesmo
espírito dos outros módulos de `barnes.db`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import psycopg


@dataclass(frozen=True)
class JobRecord:
    """Uma linha de `jobs`.

    Attributes:
        id: Id interno (Postgres) do registro.
        rq_job_id: Id do job no RQ/Redis — chave usada para correlacionar
            com `job.get_status()`/`job.meta` enquanto o Redis ainda o tiver.
        kind: Etapa do wizard que originou o job (ex.: "pose_infer").
        trial_id: Trial associado, se houver.
        status: "queued" | "started" | "finished" | "failed" — mesmo
            vocabulário de `rq.job.Job.get_status()`.
        execucao_id: Id da `execucao` produzida, quando `status == "finished"`.
        error_message: Mensagem de erro, quando `status == "failed"`.
        created_at: Quando o job foi submetido.
        started_at: Quando o worker começou a processá-lo.
        finished_at: Quando terminou (sucesso ou falha).
    """

    id: int
    rq_job_id: str
    kind: str
    trial_id: int | None
    status: str
    execucao_id: int | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


def insert_job(
    conn: psycopg.Connection, *, rq_job_id: str, kind: str, trial_id: int | None
) -> int:
    """Registra um job recém-enfileirado e devolve seu id interno.

    Args:
        conn: Conexão psycopg aberta.
        rq_job_id: Id do job no RQ (já enfileirado antes desta chamada).
        kind: Etapa do wizard que o originou.
        trial_id: Trial associado, se houver.

    Returns:
        O id interno (Postgres) do novo registro.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO jobs (rq_job_id, kind, trial_id)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (rq_job_id, kind, trial_id),
        )
        return cur.fetchone()[0]


def mark_started(conn: psycopg.Connection, rq_job_id: str) -> None:
    """Marca o job como iniciado pelo worker.

    Raises:
        ValueError: Se não existir job com esse `rq_job_id`.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET status = 'started', started_at = now() WHERE rq_job_id = %s",
            (rq_job_id,),
        )
        if cur.rowcount == 0:
            raise ValueError(f"Job {rq_job_id!r} não encontrado.")


def mark_finished(conn: psycopg.Connection, rq_job_id: str, execucao_id: int | None) -> None:
    """Marca o job como concluído com sucesso.

    Args:
        conn: Conexão psycopg aberta.
        rq_job_id: Id do job no RQ.
        execucao_id: Execução produzida por este job, se houver (nem todo
            job termina em uma `execucao` — ex.: um passo puramente de
            leitura/validação).

    Raises:
        ValueError: Se não existir job com esse `rq_job_id`.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE jobs
            SET status = 'finished', finished_at = now(), execucao_id = %s
            WHERE rq_job_id = %s
            """,
            (execucao_id, rq_job_id),
        )
        if cur.rowcount == 0:
            raise ValueError(f"Job {rq_job_id!r} não encontrado.")


def mark_failed(conn: psycopg.Connection, rq_job_id: str, error_message: str) -> None:
    """Marca o job como falho.

    Raises:
        ValueError: Se não existir job com esse `rq_job_id`.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE jobs
            SET status = 'failed', finished_at = now(), error_message = %s
            WHERE rq_job_id = %s
            """,
            (error_message, rq_job_id),
        )
        if cur.rowcount == 0:
            raise ValueError(f"Job {rq_job_id!r} não encontrado.")


def list_recent_jobs(conn: psycopg.Connection, limit: int = 50) -> list[JobRecord]:
    """Lista os jobs mais recentes, do mais novo para o mais antigo.

    Args:
        conn: Conexão psycopg aberta.
        limit: Quantidade máxima de registros.

    Returns:
        Até `limit` `JobRecord`, ordenados por `created_at` descendente.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, rq_job_id, kind, trial_id, status, execucao_id,
                   error_message, created_at, started_at, finished_at
            FROM jobs
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [JobRecord(*row) for row in cur.fetchall()]
