"""Versioned camera calibration and metric provenance in SQLite or PostgreSQL.

``camera_orientations`` identifies a fixed camera pose and video resolution.
``calibrations`` is append-only; the highest version for an orientation is active.
``executions`` keeps the calibration ID and original metric values forever. A new
calibration invalidates existing executions for that orientation in the same
transaction. PostgreSQL locks the orientation row; SQLite uses BEGIN IMMEDIATE
to serialize calibration writes with execution publication.

This initial schema uses portable SQL and is initialized idempotently. PostgreSQL
is selected by a postgresql:// / postgres:// URL or a libpq connection string;
other inputs are SQLite file paths (including :memory:).
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from numbers import Integral
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Any, Self
from uuid import uuid4

if TYPE_CHECKING:
    from barnes.io.calibration import CalibrationResult


class CalibrationRequiredError(ValueError):
    """No scale exists for the requested camera orientation."""


class StaleCalibrationError(ValueError):
    """A result cannot be published with an obsolete calibration."""


@dataclass(frozen=True)
class StoredCalibration:
    id: str
    orientation_id: str
    version: int
    result: CalibrationResult
    reference_video: str
    reference_frame: int
    reference_size: tuple[int, int]
    created_at: str

    @property
    def cm_per_px(self) -> float:
        return self.result.cm_per_px


@dataclass(frozen=True)
class StoredExecution:
    id: str
    trial_id: str
    calibration_id: str
    orientation_id: str
    metrics: dict[str, Any]
    is_valid: bool
    created_at: str
    invalidated_at: str | None


# TEXT stores lossless JSON and UTC timestamps consistently across both backends.
# The composite foreign key prevents execution provenance crossing orientations.
_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS camera_orientations (
        id TEXT PRIMARY KEY CHECK (length(trim(id)) > 0),
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS calibrations (
        id TEXT PRIMARY KEY,
        orientation_id TEXT NOT NULL REFERENCES camera_orientations(id),
        version INTEGER NOT NULL CHECK (version > 0),
        cm_per_px DOUBLE PRECISION NOT NULL CHECK (cm_per_px > 0),
        relative_disagreement DOUBLE PRECISION NOT NULL
            CHECK (relative_disagreement >= 0),
        angle_degrees DOUBLE PRECISION NOT NULL
            CHECK (angle_degrees > 0 AND angle_degrees <= 90),
        segments_json TEXT NOT NULL,
        reference_video TEXT NOT NULL CHECK (length(trim(reference_video)) > 0),
        reference_frame INTEGER NOT NULL CHECK (reference_frame >= 0),
        reference_width INTEGER NOT NULL CHECK (reference_width > 0),
        reference_height INTEGER NOT NULL CHECK (reference_height > 0),
        created_at TEXT NOT NULL,
        UNIQUE (orientation_id, version),
        UNIQUE (id, orientation_id)
    )""",
    """CREATE TABLE IF NOT EXISTS executions (
        id TEXT PRIMARY KEY,
        trial_id TEXT NOT NULL CHECK (length(trim(trial_id)) > 0),
        calibration_id TEXT NOT NULL,
        orientation_id TEXT NOT NULL,
        metrics_json TEXT NOT NULL,
        is_valid INTEGER NOT NULL CHECK (is_valid IN (0, 1)),
        created_at TEXT NOT NULL,
        invalidated_at TEXT,
        FOREIGN KEY (calibration_id, orientation_id)
            REFERENCES calibrations(id, orientation_id),
        CHECK ((is_valid = 1 AND invalidated_at IS NULL)
            OR (is_valid = 0 AND invalidated_at IS NOT NULL))
    )""",
    "CREATE INDEX IF NOT EXISTS executions_trial_idx ON executions(trial_id)",
    "CREATE INDEX IF NOT EXISTS executions_orientation_idx ON executions(orientation_id)",
)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"{field} deve ser um texto não vazio, sem caracteres nulos.")
    return value


def _integer(value: int, field: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < minimum:
        raise ValueError(f"{field} deve ser um inteiro maior ou igual a {minimum}.")
    return int(value)


def _metrics_json(metrics: dict[str, Any]) -> str:
    if not isinstance(metrics, dict):
        raise ValueError("As métricas devem ser um dicionário JSON.")  # noqa: TRY004

    def validate(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                _identifier(key, "Nome da métrica")
                validate(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                validate(item)
        elif (
            value is None
            or isinstance(value, (str, bool, int))
            or isinstance(value, float)
            and math.isfinite(value)
        ):
            return
        else:
            raise ValueError("As métricas devem conter somente valores JSON finitos.")

    try:
        validate(metrics)
        return json.dumps(metrics, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (TypeError, RecursionError) as error:
        raise ValueError("As métricas devem conter somente valores JSON finitos.") from error


class CalibrationRepository:
    """Persist scales and executions without owning or modifying source videos."""

    def __init__(self, database: str | Path):
        address = str(database)
        if not address.strip():
            raise ValueError("Informe o caminho do banco ou uma conexão PostgreSQL.")
        self._postgres = isinstance(database, str) and (
            address.startswith(("postgresql://", "postgres://"))
            or any(address.startswith(f"{key}=") for key in ("host", "dbname", "user", "service"))
        )
        self._lock = RLock()
        if self._postgres:
            import psycopg
            from psycopg import IsolationLevel
            from psycopg.rows import dict_row

            self._connection = psycopg.connect(address, autocommit=True, row_factory=dict_row)
            # Re-read the active version after acquiring the orientation lock,
            # even when the server has a different default isolation level.
            self._connection.isolation_level = IsolationLevel.READ_COMMITTED
        else:
            if address != ":memory:":
                Path(address).parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(
                address, timeout=30, isolation_level=None, check_same_thread=False
            )
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
        try:
            with self._transaction():
                if self._postgres:
                    # Concurrent application starts must not race on CREATE TABLE.
                    self._execute("SELECT pg_advisory_xact_lock(1936353586)")
                for statement in _SCHEMA:
                    self._execute(statement)
        except BaseException:
            self.close()
            raise

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _execute(self, query: str, params: tuple = ()) -> Any:
        return self._connection.execute(
            query.replace("?", "%s") if self._postgres else query, params
        )

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock:
            if self._postgres:
                with self._connection.transaction():
                    yield
            else:
                self._connection.execute("BEGIN IMMEDIATE")
                try:
                    yield
                    self._connection.commit()
                except BaseException:
                    self._connection.rollback()
                    raise

    def _lock_orientation(self, orientation_id: str) -> None:
        if self._postgres:
            self._execute(
                "SELECT id FROM camera_orientations WHERE id = ? FOR UPDATE", (orientation_id,)
            ).fetchone()

    def save_calibration(
        self,
        orientation_id: str,
        result: CalibrationResult,
        *,
        reference_video: str,
        reference_frame: int,
        reference_size: tuple[int, int],
    ) -> StoredCalibration:
        """Append a version and invalidate previous executions atomically."""
        from barnes.io.calibration import calculate_calibration

        orientation_id = _identifier(orientation_id, "Orientação de câmera")
        reference_video = _identifier(reference_video, "Vídeo de referência")
        reference_frame = _integer(reference_frame, "Quadro de referência", minimum=0)
        if not isinstance(reference_size, (tuple, list)) or len(reference_size) != 2:
            raise ValueError("Informe a resolução de referência como (largura, altura).")
        width = _integer(reference_size[0], "Largura de referência", minimum=1)
        height = _integer(reference_size[1], "Altura de referência", minimum=1)
        calculated = calculate_calibration(result.segments)
        for field in ("cm_per_px", "relative_disagreement", "angle_degrees"):
            if not math.isclose(getattr(result, field), getattr(calculated, field), rel_tol=1e-12):
                raise ValueError("A escala informada não corresponde aos segmentos de calibração.")
        for segment in calculated.segments:
            for x, y in (segment.start, segment.end):
                if not (0 <= x < width and 0 <= y < height):
                    raise ValueError("Os pontos de calibração devem estar dentro do quadro.")
        segments_json = json.dumps(
            [
                {"start": segment.start, "end": segment.end, "length_cm": segment.length_cm}
                for segment in calculated.segments
            ],
            allow_nan=False,
            separators=(",", ":"),
        )
        calibration_id = str(uuid4())
        with self._transaction():
            now = _timestamp()
            self._execute(
                "INSERT INTO camera_orientations (id, created_at) VALUES (?, ?) "
                "ON CONFLICT (id) DO NOTHING",
                (orientation_id, now),
            )
            self._lock_orientation(orientation_id)
            now = _timestamp()
            row = self._execute(
                "SELECT MAX(version) AS version FROM calibrations WHERE orientation_id = ?",
                (orientation_id,),
            ).fetchone()
            version = (row["version"] or 0) + 1
            self._execute(
                """INSERT INTO calibrations (
                    id, orientation_id, version, cm_per_px, relative_disagreement,
                    angle_degrees, segments_json, reference_video, reference_frame,
                    reference_width, reference_height, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    calibration_id,
                    orientation_id,
                    version,
                    calculated.cm_per_px,
                    calculated.relative_disagreement,
                    calculated.angle_degrees,
                    segments_json,
                    reference_video,
                    reference_frame,
                    width,
                    height,
                    now,
                ),
            )
            self._execute(
                "UPDATE executions SET is_valid = 0, invalidated_at = ? "
                "WHERE orientation_id = ? AND is_valid = 1",
                (now, orientation_id),
            )
        return StoredCalibration(
            calibration_id,
            orientation_id,
            version,
            calculated,
            reference_video,
            reference_frame,
            (width, height),
            now,
        )

    @staticmethod
    def _calibration(row: Any) -> StoredCalibration:
        from barnes.io.calibration import CalibrationResult, Segment

        segments = tuple(
            Segment(tuple(segment["start"]), tuple(segment["end"]), segment["length_cm"])
            for segment in json.loads(row["segments_json"])
        )
        return StoredCalibration(
            id=row["id"],
            orientation_id=row["orientation_id"],
            version=row["version"],
            result=CalibrationResult(
                segments=segments,
                cm_per_px=row["cm_per_px"],
                relative_disagreement=row["relative_disagreement"],
                angle_degrees=row["angle_degrees"],
            ),
            reference_video=row["reference_video"],
            reference_frame=row["reference_frame"],
            reference_size=(row["reference_width"], row["reference_height"]),
            created_at=row["created_at"],
        )

    def get_calibration(self, calibration_id: str) -> StoredCalibration | None:
        _identifier(calibration_id, "Identificador da calibração")
        with self._lock:
            row = self._execute(
                "SELECT * FROM calibrations WHERE id = ?", (calibration_id,)
            ).fetchone()
        return None if row is None else self._calibration(row)

    def get_active_calibration(self, orientation_id: str) -> StoredCalibration | None:
        _identifier(orientation_id, "Orientação de câmera")
        with self._lock:
            row = self._execute(
                "SELECT * FROM calibrations WHERE orientation_id = ? ORDER BY version DESC LIMIT 1",
                (orientation_id,),
            ).fetchone()
        return None if row is None else self._calibration(row)

    def require_calibration(self, orientation_id: str) -> StoredCalibration:
        calibration = self.get_active_calibration(orientation_id)
        if calibration is None:
            raise CalibrationRequiredError(
                f"A orientação de câmera '{orientation_id}' exige calibração antes do "
                "cálculo de distância, velocidade ou eficiência de rota."
            )
        return calibration

    def list_calibrations(self, orientation_id: str) -> list[StoredCalibration]:
        _identifier(orientation_id, "Orientação de câmera")
        with self._lock:
            rows = self._execute(
                "SELECT * FROM calibrations WHERE orientation_id = ? ORDER BY version",
                (orientation_id,),
            ).fetchall()
        return [self._calibration(row) for row in rows]

    def record_execution(
        self, trial_id: str, calibration_id: str, metrics: dict[str, Any]
    ) -> StoredExecution:
        """Publish metrics only if their calibration is still active."""
        _identifier(trial_id, "Identificador do trial")
        _identifier(calibration_id, "Identificador da calibração")
        metrics_json = _metrics_json(metrics)
        execution_id = str(uuid4())
        with self._transaction():
            calibration = self.get_calibration(calibration_id)
            if calibration is None:
                raise CalibrationRequiredError("A calibração informada não existe no banco.")
            self._lock_orientation(calibration.orientation_id)
            active = self.require_calibration(calibration.orientation_id)
            if active.id != calibration.id:
                raise StaleCalibrationError(
                    "A orientação foi recalibrada durante o processamento. "
                    "Reprocesse o trial com a escala atual."
                )
            now = _timestamp()
            self._execute(
                """INSERT INTO executions (
                    id, trial_id, calibration_id, orientation_id, metrics_json,
                    is_valid, created_at, invalidated_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?, NULL)""",
                (
                    execution_id,
                    trial_id,
                    calibration_id,
                    calibration.orientation_id,
                    metrics_json,
                    now,
                ),
            )
        return StoredExecution(
            execution_id,
            trial_id,
            calibration_id,
            calibration.orientation_id,
            json.loads(metrics_json),
            True,
            now,
            None,
        )

    @staticmethod
    def _execution(row: Any) -> StoredExecution:
        return StoredExecution(
            id=row["id"],
            trial_id=row["trial_id"],
            calibration_id=row["calibration_id"],
            orientation_id=row["orientation_id"],
            metrics=json.loads(row["metrics_json"]),
            is_valid=bool(row["is_valid"]),
            created_at=row["created_at"],
            invalidated_at=row["invalidated_at"],
        )

    def get_execution(self, execution_id: str) -> StoredExecution | None:
        _identifier(execution_id, "Identificador da execução")
        with self._lock:
            row = self._execute("SELECT * FROM executions WHERE id = ?", (execution_id,)).fetchone()
        return None if row is None else self._execution(row)

    def list_executions(self, trial_id: str | None = None) -> list[StoredExecution]:
        query = "SELECT * FROM executions"
        params = ()
        if trial_id is not None:
            _identifier(trial_id, "Identificador do trial")
            query += " WHERE trial_id = ?"
            params = (trial_id,)
        with self._lock:
            rows = self._execute(query + " ORDER BY created_at, id", params).fetchall()
        return [self._execution(row) for row in rows]
