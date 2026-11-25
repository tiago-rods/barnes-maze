"""Figuras Matplotlib sem GUI; somente snapshots fornecidos pelo banco."""

import json
import textwrap
from collections import defaultdict
from pathlib import Path
from typing import Any

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from barnes.longitudinal.learning import METRICS, summarize, usable


def provenance_lines(rows: list[dict[str, Any]]) -> list[str]:
    """Imprime todas as execuções usadas, com hashes completos e estado do código."""
    executions = {r["execucao_id"]: r for r in rows if r["execucao_id"] is not None}
    lines = []
    grouped = defaultdict(list)
    for eid, row in sorted(executions.items()):
        key = (row["model_id"], row["git_commit"], row["git_dirty"], row["limiares_sha256"])
        grouped[key].append(eid)
    for (model, commit, dirty, thresholds), ids in grouped.items():
        text = (
            f"Execuções {', '.join(map(str, ids))} | modelo={model or 'não registrado'} | "
            f"commit={commit or 'não registrado'} | sujo={dirty} | "
            f"limiares SHA256={thresholds or 'não registrado'}"
        )
        lines.extend(textwrap.wrap(text, 135))
    return lines or ["Sem execução de métricas registrada."]


def make_figure(rows: list[dict[str, Any]], *, title: str, event: str, aggregate: bool) -> Figure:
    """Quatro painéis, censura por trial e inventário de ausências por sessão."""
    footer = provenance_lines(rows)
    for session in sorted({r["session"] for r in rows}):
        subset = [r for r in rows if r["session"] == session]
        footer.append(
            f"Sessão {session}: censurados={sum(r['observed'] is False for r in subset)}, "
            f"não avaliados={sum(r['observed'] is None for r in subset)}, "
            f"obsoletos={sum(bool(r['stale']) for r in subset)}"
        )
    qualities = sorted({r.get("pose_quality") or "não avaliada" for r in rows})
    footer.append("Qualidade de pose atual: " + ", ".join(qualities))
    footer.append("Execuções distintas podem usar modelos/limiares distintos; confira o manifesto.")
    footer_height = max(0.8, len(footer) * 0.15 + 0.25)
    height = 9 + footer_height
    fig = Figure(figsize=(13, height))
    FigureCanvasAgg(fig)
    axes = fig.subplots(2, 2).flat
    sessions = sorted({r["session"] for r in rows})
    for ax, (metric, label) in zip(axes, METRICS.items(), strict=True):
        summary = summarize(rows, metric)
        points = summary["aggregate"] if aggregate else summary["animals"]
        values = {p["session"]: p["mean"] for p in points}
        ax.plot(
            sessions,
            [values.get(s, float("nan")) for s in sessions],
            "o-",
            label="Média dos animais (sucessos)" if aggregate else "Média dos sucessos",
        )
        if aggregate:
            dispersed = [p for p in points if p["sd"] is not None]
            ax.errorbar(
                [p["session"] for p in dispersed],
                [p["mean"] for p in dispersed],
                yerr=[p["sd"] for p in dispersed],
                fmt="none",
                capsize=4,
                label="± DP entre animais (n ≥ 2)",
            )
        censored = [
            r for r in rows if r["observed"] is False and not r["stale"] and usable(r[metric])
        ]
        ax.scatter(
            [r["session"] for r in censored],
            [r[metric] for r in censored],
            marker="^",
            facecolors="none",
            edgecolors="darkorange",
            label="Censurado: valor observado parcial",
        )
        unknown = [
            r for r in rows if r["observed"] is None and not r["stale"] and usable(r[metric])
        ]
        ax.scatter(
            [r["session"] for r in unknown],
            [r[metric] for r in unknown],
            marker="x",
            color="gray",
            label="Censura não avaliada (fora da média)",
        )
        label = "Erros totais do trial" if metric == "errors" and event == "total" else label
        ax.set_title(label)
        for point in points:
            n = point["n_animals"] if aggregate else point["n_trials"]
            ax.annotate(
                f"n={n}",
                (point["session"], point["mean"]),
                xytext=(4, 7),
                textcoords="offset points",
                fontsize=7,
            )
        ax.set_xlabel("Número da sessão")
        ax.set_ylabel(label)
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.grid(alpha=0.25)
        ax.legend(fontsize=7)
        ax.text(
            0,
            -0.20,
            f"Sem valor: {sum(not usable(r[metric]) for r in rows)} trials. n = animais"
            if aggregate
            else f"Sem valor: {sum(not usable(r[metric]) for r in rows)} trials. n = trials",
            transform=ax.transAxes,
            fontsize=7,
            va="top",
        )
        if not points:
            ax.text(0.5, 0.5, "Sem valores completos válidos", transform=ax.transAxes, ha="center")
    fig.suptitle(
        f"{title} — evento {event}\n"
        "Curvas descritivas condicionadas ao sucesso; censura não entra na média.",
        fontsize=13,
        y=1 - 0.1 / height,
    )
    fig.subplots_adjust(
        top=1 - 1.2 / height, bottom=(footer_height + 1) / height, hspace=0.60, wspace=0.25
    )
    fig.text(0.03, 0.02, "\n".join(footer), fontsize=6.5, va="bottom", family="monospace")
    return fig


def export_learning(
    rows: list[dict[str, Any]],
    directory: str | Path,
    *,
    phase: str = "acquisition",
    event: str = "primary",
) -> Path:
    """Exporta PNG/PDF/SVG e snapshot JSON; diretório deve ser novo."""
    if not rows:
        raise ValueError("Nenhum trial encontrado para os filtros informados.")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": 1,
        "phase": phase,
        "event": event,
        "aggregation": "mean of animal means; sample SD; successes only",
        "rows": rows,
        "summaries": {m: summarize(rows, m) for m in METRICS},
        "figures": [],
    }
    cohorts = [("grupo", rows, True)]
    cohorts.extend(
        (f"animal-{animal}", [r for r in rows if r["animal_id"] == animal], False)
        for animal in sorted({r["animal_id"] for r in rows})
    )
    try:
        for name, cohort, aggregate in cohorts:
            title = (
                f"Grupo selecionado ({phase})"
                if aggregate
                else (f"Animal {cohort[0]['animal_name']} / ID {cohort[0]['animal_id']} ({phase})")
            )
            fig = make_figure(cohort, title=title, event=event, aggregate=aggregate)
            try:
                for extension in ("png", "pdf", "svg"):
                    filename = f"{name}.{extension}"
                    fig.savefig(directory / filename, dpi=160, bbox_inches="tight")
                    manifest["figures"].append(filename)
            finally:
                fig.clear()
        (directory / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
        )
    except Exception:
        # Só artefatos desta chamada, dentro do diretório recém-criado.
        for child in directory.iterdir():
            if child.is_file():
                child.unlink()
        directory.rmdir()
        raise
    return directory
