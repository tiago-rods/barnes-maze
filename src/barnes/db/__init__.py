"""Acesso ao banco de dados PostgreSQL do projeto."""

from barnes.db.connection import DatabaseConfigError, apply_migrations, get_connection

# TODO(Tiago): repositório da US-02 (SQLite/Postgres com schema próprio) ainda fora
# do padrão de migrações + `conn`; reexportado aqui só para não quebrar os imports.
from barnes.db.repository import (
    CalibrationRepository,
    CalibrationRequiredError,
    StaleCalibrationError,
    StoredCalibration,
    StoredExecution,
)
from barnes.db.trials import insert_trial

__all__ = [
    "CalibrationRepository",
    "CalibrationRequiredError",
    "DatabaseConfigError",
    "StaleCalibrationError",
    "StoredCalibration",
    "StoredExecution",
    "apply_migrations",
    "get_connection",
    "insert_trial",
]
