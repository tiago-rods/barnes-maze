"""`GET /api/catalog` — status de processamento por trial (US-27 RN03)."""

from __future__ import annotations

from typing import Literal

import psycopg
from fastapi import APIRouter, Depends

from barnes.db.catalog import list_catalog

from ..deps import get_db
from ..schemas.catalog import CatalogEntry

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("", response_model=list[CatalogEntry])
def get_catalog(
    experiment_id: int | None = None,
    verify: Literal["size", "hash"] | None = None,
    conn: psycopg.Connection = Depends(get_db),
) -> list[CatalogEntry]:
    rows = list_catalog(conn, experiment_id=experiment_id, verify=verify)
    return [CatalogEntry.model_validate(row, from_attributes=True) for row in rows]
