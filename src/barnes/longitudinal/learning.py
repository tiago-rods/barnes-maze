"""Curvas descritivas US-22; censurados separados, sem estimador de sobrevivência."""

from collections import defaultdict
from math import isfinite
from statistics import mean, stdev
from typing import Any

METRICS = {
    "latency": "Latência ao alvo (s)",
    "errors": "Erros até o alvo",
    "distance": "Distância do trial (cm)",
    "entropy": "Entropia (bits)",
}


def usable(value: object) -> bool:
    """Valor disponível e finito; ausência não vira zero."""
    return isinstance(value, int | float) and not isinstance(value, bool) and isfinite(value)


def summarize(rows: list[dict[str, Any]], metric: str) -> dict[str, list[dict]]:
    """Média por animal/sessão e média ± DP amostral entre animais.

    Inclui somente sucessos com resultado vigente; censura/estado desconhecido
    permanecem no relatório/figura. Cada animal tem peso igual na agregação.
    """
    if metric not in METRICS:
        raise ValueError("Métrica inválida.")
    grouped = defaultdict(list)
    for row in rows:
        if row["observed"] is True and not row["stale"] and usable(row[metric]):
            grouped[(row["animal_id"], row["session"])].append(row[metric])
    animals = [
        {"animal_id": animal, "session": session, "mean": mean(values), "n_trials": len(values)}
        for (animal, session), values in sorted(grouped.items())
    ]
    sessions = defaultdict(list)
    for point in animals:
        sessions[point["session"]].append(point["mean"])
    aggregate = [
        {
            "session": session,
            "mean": mean(values),
            "sd": stdev(values) if len(values) > 1 else None,
            "n_animals": len(values),
        }
        for session, values in sorted(sessions.items())
    ]
    return {"animals": animals, "aggregate": aggregate}
