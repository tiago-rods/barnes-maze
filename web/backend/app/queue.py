"""Fila RQ (Redis), compartilhada pelos routers (enfileiram) e pelo worker (processa)."""

from __future__ import annotations

import redis
from rq import Queue

from .config import REDIS_URL

redis_conn = redis.Redis.from_url(REDIS_URL)
queue = Queue("default", connection=redis_conn)
