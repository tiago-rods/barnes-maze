"""Configuração do backend, lida do mesmo `.env` do resto do repositório."""

from __future__ import annotations

import os
from pathlib import Path

from barnes.db.connection import load_local_env

load_local_env()

REDIS_URL = os.environ.get("BARNES_REDIS_URL", "redis://localhost:6380/0")
"""Porta 6380 por padrão, para casar com o serviço `redis` do docker-compose.yml."""

VIDEO_DATA_DIR = Path(os.environ.get("BARNES_VIDEO_DATA_DIR", "./data"))
"""Raiz onde `GET /api/videos` procura `.mp4`. `data/` é gitignorada e por
máquina — nunca assumir seu conteúdo, só o caminho configurável."""
