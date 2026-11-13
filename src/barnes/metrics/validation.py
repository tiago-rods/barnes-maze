"""Correlação da distância automática com a medida manual de referência (US-18 RN06).

Puro, sem banco: lê o CSV da medida manual, pareia com as distâncias automáticas que a
CLI lê de `trial_results` e calcula o r de Pearson. O critério de aceite do card é
**r ≥ 0,95** — constante do card, não um limiar operacional do laboratório, por isso
fica no código e não em `configs/default.yaml` (que é do portão G3).

r alto não garante escala certa: uma distância automática sistematicamente 20% maior
ainda dá r = 1. Por isso o relatório leva também o viés médio e o erro relativo médio,
para que quem aceita veja os dois.

Enquanto a referência manual não existir (ver pendências em
`docs/definicoes-metricas.md`), a rodada é registrada como bloqueada, no mesmo espírito
da calibração de eventos da US-12/US-13: a ferramenta está pronta, o aceite não.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from math import isfinite
from pathlib import Path
from typing import Any

import numpy as np

R_THRESHOLD = 0.95
MIN_PAIRS = 3
MANUAL_COLUMNS = ("trial_id", "distance_cm_manual", "observador", "metodo", "data")


class ManualDistanceError(ValueError):
    """CSV da medida manual ausente, fora do formato ou com valores inválidos."""


@dataclass(frozen=True)
class ManualDistance:
    """Uma distância medida à mão, com quem mediu e como."""

    trial_id: int
    distance_cm: float
    observador: str
    metodo: str
    data: str


@dataclass(frozen=True)
class DistancePair:
    trial_id: int
    manual_cm: float
    automatico_cm: float


@dataclass(frozen=True)
class DistanceCorrelation:
    """Resultado de uma rodada de comparação.

    Attributes:
        n: Pares usados.
        r: Coeficiente de Pearson.
        limiar: r mínimo do card (0,95).
        aprovado: `r >= limiar`.
        vies_medio_cm: Média de (automático − manual).
        erro_relativo_medio: Média de |automático − manual| / manual (pares com manual > 0).
        pares: Pares usados.
        excluidos: `(trial_id, motivo)` dos trials da referência que ficaram de fora.
    """

    n: int
    r: float
    limiar: float
    aprovado: bool
    vies_medio_cm: float
    erro_relativo_medio: float | None
    pares: tuple[DistancePair, ...]
    excluidos: tuple[tuple[int, str], ...]

    def as_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["status"] = "aprovado" if self.aprovado else "reprovado"
        record["excluidos"] = [{"trial_id": t, "motivo": m} for t, m in self.excluidos]
        return record


def load_manual_distances(path: str | Path) -> tuple[ManualDistance, ...]:
    """Lê o CSV da referência manual (`trial_id,distance_cm_manual,observador,metodo,data`).

    Raises:
        ManualDistanceError: Arquivo ausente, colunas faltando, trial repetido, ou
            distância não numérica, não finita ou negativa.
    """
    path = Path(path)
    if not path.is_file():
        raise ManualDistanceError(f"Referência manual não encontrada: {path}")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = [c for c in MANUAL_COLUMNS if c not in (reader.fieldnames or ())]
        if missing:
            raise ManualDistanceError(
                f"{path}: faltam as colunas {', '.join(missing)} "
                f"(esperado: {','.join(MANUAL_COLUMNS)})."
            )
        rows: list[ManualDistance] = []
        seen: set[int] = set()
        for row in reader:
            line = reader.line_num
            try:
                trial_id = int(row["trial_id"])
                distance = float(row["distance_cm_manual"])
            except (TypeError, ValueError) as exc:
                raise ManualDistanceError(f"{path}, linha {line}: valor não numérico.") from exc
            if not isfinite(distance) or distance < 0:
                raise ManualDistanceError(
                    f"{path}, linha {line}: distância deve ser finita e não negativa."
                )
            if trial_id in seen:
                raise ManualDistanceError(f"{path}, linha {line}: trial {trial_id} repetido.")
            seen.add(trial_id)
            rows.append(
                ManualDistance(
                    trial_id=trial_id,
                    distance_cm=distance,
                    observador=(row["observador"] or "").strip(),
                    metodo=(row["metodo"] or "").strip(),
                    data=(row["data"] or "").strip(),
                )
            )
    if not rows:
        raise ManualDistanceError(f"{path}: nenhuma medida manual.")
    return tuple(rows)


def correlate_distances(
    pairs: Iterable[DistancePair],
    *,
    excluded: Iterable[tuple[int, str]] = (),
    threshold: float = R_THRESHOLD,
) -> DistanceCorrelation:
    """r de Pearson entre distância automática e manual (US-18 Cenário 2).

    Raises:
        ValueError: Menos de `MIN_PAIRS` pares, ou uma das séries sem variação (r
            indefinido — não é zero nem um).
    """
    pairs = tuple(pairs)
    if len(pairs) < MIN_PAIRS:
        raise ValueError(
            f"São necessários ao menos {MIN_PAIRS} trials com medida manual e automática "
            f"para a correlação; há {len(pairs)}."
        )
    manual = np.array([p.manual_cm for p in pairs], dtype=float)
    auto = np.array([p.automatico_cm for p in pairs], dtype=float)
    if np.ptp(manual) == 0 or np.ptp(auto) == 0:
        raise ValueError(
            "Uma das séries não varia entre os trials: a correlação é indefinida. A "
            "referência precisa cobrir buscas curtas e longas."
        )
    r = float(np.corrcoef(manual, auto)[0, 1])
    positive = manual > 0
    relative = (
        float(np.mean(np.abs(auto[positive] - manual[positive]) / manual[positive]))
        if positive.any()
        else None
    )
    return DistanceCorrelation(
        n=len(pairs),
        r=r,
        limiar=threshold,
        aprovado=r >= threshold,
        vies_medio_cm=float(np.mean(auto - manual)),
        erro_relativo_medio=relative,
        pares=pairs,
        excluidos=tuple(excluded),
    )


def blocked_record(reason: str) -> dict[str, Any]:
    """Registro de rodada sem referência manual: aceite bloqueado, nada calculado."""
    return {
        "status": "bloqueado",
        "motivo": reason,
        "limiar": R_THRESHOLD,
        "proxima_acao": (
            "Obter a medida manual de distância (pendências da SCRUM-225 em "
            "docs/definicoes-metricas.md) e repetir a rodada."
        ),
    }


def render_markdown(record: dict[str, Any]) -> str:
    """Relatório legível de uma rodada (aprovada, reprovada ou bloqueada)."""
    lines = ["# US-18 — correlação da distância com a referência manual", ""]
    lines.append(f"- Status: **{record['status']}**")
    lines.append(f"- Critério: r ≥ {record['limiar']:.2f}")
    if record["status"] == "bloqueado":
        lines += [f"- Motivo: {record['motivo']}", f"- Próxima ação: {record['proxima_acao']}"]
        return "\n".join(lines) + "\n"
    relative = record["erro_relativo_medio"]
    lines += [
        f"- n = {record['n']} trials · r = {record['r']:.4f}",
        f"- Viés médio (automático − manual): {record['vies_medio_cm']:+.2f} cm",
        "- Erro relativo médio: " + ("—" if relative is None else f"{relative:.1%}"),
        "",
        "| trial | manual (cm) | automático (cm) |",
        "|---:|---:|---:|",
    ]
    lines += [
        f"| {p['trial_id']} | {p['manual_cm']:.2f} | {p['automatico_cm']:.2f} |"
        for p in record["pares"]
    ]
    if record["excluidos"]:
        lines += ["", "Trials da referência fora da comparação:", ""]
        lines += [f"- {e['trial_id']}: {e['motivo']}" for e in record["excluidos"]]
    return "\n".join(lines) + "\n"
