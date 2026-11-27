"""Processo worker do RQ: `uv run python -m web.backend.worker`.

Usa `SimpleWorker` (processa no próprio processo, sem `fork`) porque o RQ
`Worker` padrão depende de `os.fork`, indisponível no Windows — máquina de
desenvolvimento desta equipe. Para uma ferramenta local de um único
usuário, o isolamento extra de processo por job do `Worker` padrão não é
necessário.

Importa os módulos de `app.jobs` para que o RQ encontre (desserialize) as
funções enfileiradas pelos routers.
"""

from __future__ import annotations

from rq import SimpleWorker

from web.backend.app.jobs import (  # noqa: F401  (necessário para desserializar os jobs)
    pose_jobs,
    video_jobs,
)
from web.backend.app.queue import redis_conn

if __name__ == "__main__":
    worker = SimpleWorker(["default"], connection=redis_conn)
    worker.work()
