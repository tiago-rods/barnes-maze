"""Enfileiramento rastreado: registro em `jobs` comitado ANTES do job entrar na fila.

Antes, routers e jobs encadeados faziam `queue.enqueue(...)` e só depois
`insert_job(...)` — e o commit da linha só acontecia no fim da requisição.
O worker pega o job do Redis em milissegundos, chama `mark_started` e não
acha a linha ("Job não encontrado"): o job quebrava e o registro ficava
`queued` para sempre na tela. Aqui o id do RQ é gerado antes, a linha é
gravada e comitada numa conexão própria, e só então o job é enfileirado.

`on_job_failure` cobre exceções que os jobs não tratam (ex.: `ImportError`
do SLEAP ausente): sem ela, o registro ficaria `started` para sempre.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from rq import Callback

from barnes.db.connection import get_connection
from barnes.db.jobs import get_job_by_rq_id, insert_job, mark_failed

from ..queue import queue

TERMINAL_STATUSES = frozenset({"finished", "failed"})


def enqueue_tracked(
    func: Callable[..., Any],
    job_kwargs: dict[str, Any],
    *,
    kind: str,
    trial_id: int | None,
) -> int:
    """Registra o job em `jobs` (comitado) e só então o enfileira no RQ.

    Args:
        func: Função do job (importável pelo worker).
        job_kwargs: Argumentos nomeados do job; um `dsn` ali também é usado
            para o registro em `jobs` (`None`/ausente = `BARNES_DATABASE_URL`).
        kind: Etapa do wizard (`jobs.kind`).
        trial_id: Trial associado, se houver (só para o registro).

    Returns:
        O id interno (Postgres) do registro, usado no polling do frontend.
    """
    dsn = job_kwargs.get("dsn")
    rq_job_id = uuid.uuid4().hex
    with get_connection(dsn) as conn:
        job_id = insert_job(conn, rq_job_id=rq_job_id, kind=kind, trial_id=trial_id)
    try:
        queue.enqueue(
            func,
            job_id=rq_job_id,
            on_failure=Callback(on_job_failure),
            kwargs=job_kwargs,
        )
    except Exception as exc:
        with get_connection(dsn) as conn:
            mark_failed(conn, rq_job_id, f"Falha ao enfileirar: {exc}")
        raise
    return job_id


def on_job_failure(job, connection, exc_type, exc_value, traceback) -> None:
    """Callback do RQ: marca `failed` se o próprio job não marcou."""
    dsn = job.kwargs.get("dsn") if isinstance(job.kwargs, dict) else None
    with get_connection(dsn) as conn:
        record = get_job_by_rq_id(conn, job.id)
        if record is None or record.status in TERMINAL_STATUSES:
            return
        message = str(exc_value) or exc_type.__name__
        if isinstance(exc_value, ImportError):
            message = f"Dependência ausente: {message}"
        mark_failed(conn, job.id, message)
