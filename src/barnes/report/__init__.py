from __future__ import annotations

import csv
from collections.abc import Iterable, Sequence
from pathlib import Path

MISSING = ""
CM_TO_M = 0.01


def cm_to_m(value_cm: float | None) -> float | None:
    return None if value_cm is None else value_cm * CM_TO_M


def with_missing_marker(row: dict) -> dict:
    return {key: (MISSING if value is None else value) for key, value in row.items()}


def write_csv(rows: Iterable[dict], path: Path, columns: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(columns))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
