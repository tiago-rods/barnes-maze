"""Comparação local contra anotações D3 e rodadas auditáveis (US-12/US-13).

Não inventa anotações, ajusta limiares nem modifica detectores. Descobertas
são únicas por buraco; entradas repetidas são pareadas pela ordem temporal
em cada buraco. Não há busca do vizinho mais próximo para esconder eventos
faltantes ou desvios. Aprovação numérica nunca representa aceite do PI/G3.
"""

from __future__ import annotations

import json
import math
import re
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from barnes.pose.dataset import file_sha256

TOLERANCES_SECONDS = {"descoberta": 0.5, "entrada": 0.3}
TIME_ORIGIN = "intervalo_util"


class CalibrationError(ValueError):
    """Anotação, rodada ou proveniência insuficiente/inválida para comparar eventos."""


def _kind(value: Any) -> str:
    if not isinstance(value, str) or value not in TOLERANCES_SECONDS:
        raise CalibrationError("tipo deve ser 'descoberta' ou 'entrada'.")
    return value


def _integer(value: Any, name: str, minimum: int = 0) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CalibrationError(f"{name} deve ser inteiro >= {minimum}, sem booleanos.")


def _text(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise CalibrationError(f"{name} deve ser texto não vazio.")


def _sha256(value: str | None, name: str) -> None:
    if value is not None and (
        not isinstance(value, str) or re.fullmatch(r"[a-fA-F0-9]{64}", value) is None
    ):
        raise CalibrationError(f"{name} deve ser um SHA-256 hexadecimal completo ou null.")


@dataclass(frozen=True)
class ManualEvent:
    """Um evento observado; ``t_s`` usa o início do intervalo útil como zero."""

    tipo: str
    hole_number: int
    t_s: float

    def __post_init__(self) -> None:
        _kind(self.tipo)
        _integer(self.hole_number, "hole_number")
        if isinstance(self.t_s, bool) or not isinstance(self.t_s, int | float):
            raise CalibrationError("t_s deve ser número finito >= 0, sem booleanos.")
        try:
            seconds = float(self.t_s)
        except (ValueError, OverflowError) as exc:
            raise CalibrationError("t_s excede o intervalo numérico finito suportado.") from exc
        if not math.isfinite(seconds) or seconds < 0:
            raise CalibrationError("t_s deve ser número finito >= 0, sem booleanos.")
        object.__setattr__(self, "t_s", seconds)


def _validate_events(events: tuple[ManualEvent, ...], source: str) -> None:
    discoveries: set[int] = set()
    exact: set[tuple[str, int, float]] = set()
    for event in events:
        if not isinstance(event, ManualEvent):
            raise CalibrationError(f"{source}: esperado ManualEvent em cada evento.")
        key = (event.tipo, event.hole_number, event.t_s)
        if key in exact or (event.tipo == "descoberta" and event.hole_number in discoveries):
            raise CalibrationError(
                f"{source}: evento duplicado de {event.tipo} no buraco {event.hole_number}."
            )
        exact.add(key)
        if event.tipo == "descoberta":
            discoveries.add(event.hole_number)


@dataclass(frozen=True)
class ManualAnnotations:
    """Referência D3 declarada pelo laboratório; valida estrutura, não autenticidade.

    ``source`` identifica a entrega original (arquivo/documento/protocolo),
    ``observer`` identifica o observador treinado e ``delivered_on`` registra
    a data ISO YYYY-MM-DD. O hash do vídeo é opcional para entregas externas
    que não o disponibilizem. A CLI deve conferir trial, buracos e intervalo.
    """

    trial_id: int
    observer: str
    source: str
    delivered_on: str
    time_origin: str
    events: tuple[ManualEvent, ...]
    video_sha256: str | None = None
    source_path: str | None = None
    source_sha256: str | None = None

    def __post_init__(self) -> None:
        _integer(self.trial_id, "trial_id", 1)
        _text(self.observer, "observer")
        _text(self.source, "source/reference")
        if (
            not isinstance(self.delivered_on, str)
            or re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.delivered_on) is None
        ):
            raise CalibrationError("delivered_on exige data ISO YYYY-MM-DD.")
        try:
            date.fromisoformat(self.delivered_on)
        except ValueError as exc:
            raise CalibrationError("delivered_on contém uma data inexistente.") from exc
        if self.time_origin != TIME_ORIGIN:
            raise CalibrationError(
                "time_origin deve ser 'intervalo_util'; não há conversão implícita."
            )
        if not isinstance(self.events, tuple | list) or not self.events:
            raise CalibrationError(
                "D3 exige anotações manuais não vazias; não improvise uma referência."
            )
        object.__setattr__(self, "events", tuple(self.events))
        _validate_events(self.events, "D3")
        _sha256(self.video_sha256, "video_sha256")
        _sha256(self.source_sha256, "source_sha256")
        if self.video_sha256 is not None:
            object.__setattr__(self, "video_sha256", self.video_sha256.lower())


def _json_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CalibrationError(f"Chave JSON duplicada: {key}.")
        result[key] = value
    return result


def _parse_event(row: Mapping, source: str) -> ManualEvent:
    if not isinstance(row, Mapping) or not {"tipo", "hole_number", "t_s"}.issubset(row):
        raise CalibrationError(f"{source}: cada evento exige tipo, hole_number e t_s.")
    return ManualEvent(row["tipo"], row["hole_number"], row["t_s"])


def load_manual_annotations(path: str | Path) -> ManualAnnotations:
    """Lê JSON D3 local com proveniência obrigatória e preserva seu hash.

    Aceita ``reference`` como alias de ``source``; se ambos existirem devem
    ser iguais. ``schema_version`` pode ser omitido (versão 1). Nunca cria
    rótulos substitutos quando a entrega está ausente ou incompleta.
    """
    path = Path(path)
    try:
        digest = file_sha256(path)
        document = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_json_object)
        if file_sha256(path) != digest:
            raise CalibrationError(
                "Arquivo D3 mudou durante a leitura; repita com uma cópia estável."
            )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CalibrationError(f"Não foi possível ler a anotação D3: {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise CalibrationError("Anotação D3 deve ser um objeto JSON.")
    version = document.get("schema_version", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        raise CalibrationError("schema_version D3 deve ser 1.")
    source = document.get("source", document.get("reference"))
    if "source" in document and "reference" in document and source != document["reference"]:
        raise CalibrationError("source e reference não podem identificar entregas diferentes.")
    rows = document.get("events")
    if not isinstance(rows, list) or not rows:
        raise CalibrationError("D3 exige events como lista não vazia de anotações manuais.")
    return ManualAnnotations(
        trial_id=document.get("trial_id"),
        observer=document.get("observer"),
        source=source,
        delivered_on=document.get("delivered_on"),
        time_origin=document.get("time_origin"),
        events=tuple(_parse_event(row, "D3") for row in rows),
        video_sha256=document.get("video_sha256"),
        source_path=str(path.resolve()),
        source_sha256=digest,
    )


def _base_report(trial_id: int | None, kind: str) -> dict:
    _kind(kind)
    if trial_id is not None:
        _integer(trial_id, "trial_id", 1)
    return {
        "schema_version": 1,
        "story": "US-12" if kind == "descoberta" else "US-13",
        "trial_id": trial_id,
        "kind": kind,
        "time_origin": TIME_ORIGIN,
        "tolerance_s": TOLERANCES_SECONDS[kind],
        "comparison": "absolute_error_less_than_or_equal_to_tolerance",
        "matching": "chronological_occurrence_per_hole_and_kind; no_nearest_neighbor",
        "client_approval": False,
        "acceptance_scope": "comparação temporal desta rodada; aceite por escrito de PI/G3 é separado",
    }


def compare_events(
    manual: ManualAnnotations,
    automatic: Iterable[Mapping[str, Any]],
    *,
    kind: str,
) -> dict:
    """Compara um tipo de evento por rodada, com tolerância inclusiva por par.

    A identidade do trial, seus buracos e o intervalo útil dos eventos devem
    ser conferidos pelo chamador. Eventos do outro tipo são validados, mas
    não participam desta rodada. Entradas repetidas no mesmo buraco usam a
    ordem cronológica, independentemente da proximidade entre timestamps.
    Quantidade divergente, ausência ou evento inesperado sempre reprovam.
    """
    if not isinstance(manual, ManualAnnotations):
        raise CalibrationError("É necessária uma referência ManualAnnotations válida de D3.")
    _kind(kind)
    try:
        rows = iter(automatic)
    except TypeError as exc:
        raise CalibrationError("Automático: esperado um conjunto iterável de eventos.") from exc
    automatic_events = tuple(_parse_event(row, "Automático") for row in rows)
    _validate_events(automatic_events, "Automático")
    reference = [event for event in manual.events if event.tipo == kind]
    detected = [event for event in automatic_events if event.tipo == kind]
    if not reference:
        raise CalibrationError(f"D3 não contém anotações de {kind} para avaliar esta rodada.")
    by_hole_manual, by_hole_auto = defaultdict(list), defaultdict(list)
    for event in reference:
        by_hole_manual[event.hole_number].append(event.t_s)
    for event in detected:
        by_hole_auto[event.hole_number].append(event.t_s)
    comparisons = []
    tolerance = Decimal(str(TOLERANCES_SECONDS[kind]))
    for hole in sorted(by_hole_manual.keys() | by_hole_auto.keys()):
        observed = sorted(by_hole_manual[hole])
        predicted = sorted(by_hole_auto[hole])
        for occurrence in range(max(len(observed), len(predicted))):
            manual_time = observed[occurrence] if occurrence < len(observed) else None
            auto_time = predicted[occurrence] if occurrence < len(predicted) else None
            delta = None
            if manual_time is None:
                status = "unexpected_automatic"
            elif auto_time is None:
                status = "missing_automatic"
            else:
                # Evita que 10.3 - 10.0 reprove artificialmente o limite inclusivo de 0,3.
                delta = Decimal(str(auto_time)) - Decimal(str(manual_time))
                status = "within_tolerance" if abs(delta) <= tolerance else "outside_tolerance"
            comparisons.append(
                {
                    "tipo": kind,
                    "hole_number": hole,
                    "occurrence": occurrence + 1,
                    "manual_t_s": manual_time,
                    "automatic_t_s": auto_time,
                    "signed_error_s": float(delta) if delta is not None else None,
                    "absolute_error_s": float(abs(delta)) if delta is not None else None,
                    "status": status,
                    "passed": status == "within_tolerance",
                }
            )
    passed = all(pair["passed"] for pair in comparisons)
    report = _base_report(manual.trial_id, kind)
    report.update(
        status="passed" if passed else "divergence_review_required",
        passed=passed,
        manual_annotations={
            "observer": manual.observer,
            "source": manual.source,
            "delivered_on": manual.delivered_on,
            "source_path": manual.source_path,
            "source_sha256": manual.source_sha256,
            "video_sha256": manual.video_sha256,
        },
        comparisons=comparisons,
        summary={
            "manual_events": len(reference),
            "automatic_events": len(detected),
            "matched_events": sum(pair["signed_error_s"] is not None for pair in comparisons),
            **{
                status: sum(pair["status"] == status for pair in comparisons)
                for status in (
                    "within_tolerance",
                    "outside_tolerance",
                    "missing_automatic",
                    "unexpected_automatic",
                )
            },
            "max_absolute_error_s": max(
                (
                    pair["absolute_error_s"]
                    for pair in comparisons
                    if pair["absolute_error_s"] is not None
                ),
                default=None,
            ),
            "ignored_other_kind_manual": len(manual.events) - len(reference),
            "ignored_other_kind_automatic": len(automatic_events) - len(detected),
        },
        next_action=(
            "Anexar evidência e limiares ao documento de definições para aceite escrito do PI/G3."
            if passed
            else "Revisar divergências e definição operacional com o PI; ajustar somente a configuração "
            "e executar nova rodada preservando esta evidência. Nenhuma comunicação foi enviada."
        ),
    )
    return report


def blocked_round(
    *,
    trial_id: int | None,
    kind: str,
    reason: str = "Anotação manual D3 do laboratório não entregue ou não confirmada.",
) -> dict:
    """Registra a dependência externa, sem executar comparação ou inventar referência."""
    _text(reason, "reason")
    report = _base_report(trial_id, kind)
    report.update(
        status="blocked_missing_d3",
        passed=False,
        blocked_on=["D3"],
        reason=reason,
        manual_annotations=None,
        comparisons=[],
        summary=None,
        next_action="Acordar e registrar a entrega D3 pelo laboratório; não substituir por anotação improvisada.",
    )
    return report


def _markdown(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def render_evidence(report: Mapping[str, Any]) -> str:
    """Produz evidência em Markdown para anexar a docs/definicoes-metricas.md."""
    lines = [
        f"# {report['story']} — rodada de {report['kind']}",
        "",
        f"- Rodada: {_markdown(report.get('round_id', 'ainda não salva'))}",
        f"- Trial: {_markdown(report['trial_id'])}",
        f"- Estado: {_markdown(report['status'])}",
        f"- Tolerância por evento: <= {report['tolerance_s']} s (inclusiva).",
        "- Origem dos tempos: início do intervalo útil; erro assinado = automático − manual.",
        "- Pareamento: ocorrência cronológica por buraco/tipo; sem rematching por proximidade.",
        "- Aceite do cliente/PI/G3: **não concedido por esta rodada**.",
        "",
    ]
    manual = report.get("manual_annotations")
    if manual:
        lines.extend(
            [
                (
                    f"Observador D3: {_markdown(manual['observer'])}. "
                    f"Entrega: {_markdown(manual['delivered_on'])}. Fonte: {_markdown(manual['source'])}."
                ),
                f"SHA-256 da anotação: {_markdown(manual.get('source_sha256') or 'não fornecido na API')}",
                "",
                "| Buraco | Ocorrência | Manual (s) | Automático (s) | Erro assinado (s) | Erro absoluto (s) | Estado |",
                "| ---: | ---: | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for pair in report["comparisons"]:
            values = [
                pair[key]
                for key in (
                    "hole_number",
                    "occurrence",
                    "manual_t_s",
                    "automatic_t_s",
                    "signed_error_s",
                    "absolute_error_s",
                    "status",
                )
            ]
            lines.append(
                "| "
                + " | ".join("—" if value is None else _markdown(value) for value in values)
                + " |"
            )
    else:
        lines.extend([f"Bloqueio externo D3: {_markdown(report.get('reason', 'sem entrega'))}", ""])
    if report.get("consistency_issues"):
        lines.extend(["", "Inconsistências que impedem aprovação:", ""])
        lines.extend(f"- {_markdown(issue)}" for issue in report["consistency_issues"])
    lines.extend(["", report["next_action"], ""])
    if "provenance" in report:
        # JSON legível mantém valores null e hashes integrais do snapshot recebido.
        lines.extend(
            [
                "## Proveniência e limiares testados",
                "",
                "```json",
                json.dumps(report["provenance"], ensure_ascii=False, indent=2, allow_nan=False),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def _validate_saved_round(report: dict) -> None:
    """Recalcula a comparação antes de aceitar uma evidência salva.

    Confere coerência interna, não autentica D3 nem concede aceite G3.
    A validação usa os tempos preservados, sem exigir que os caminhos originais
    ainda estejam disponíveis na máquina que consulta o relatório.
    """
    if not isinstance(report, dict):
        raise CalibrationError("Rodada deve ser um objeto JSON.")
    _integer(report.get("schema_version"), "schema_version", 1)
    if report["schema_version"] != 1:
        raise CalibrationError("Versão de rodada não suportada.")
    base = _base_report(report["trial_id"], report["kind"])
    for key in ("story", "time_origin", "tolerance_s", "comparison", "matching"):
        if report.get(key) != base[key]:
            raise CalibrationError(f"Rodada com {key} incompatível com o critério implementado.")
    if report.get("client_approval") is not False:
        raise CalibrationError("Rodadas numéricas não podem conceder aceite do cliente/G3.")
    uuid.UUID(report["round_id"])
    if datetime.fromisoformat(report["created_at"]).tzinfo is None:
        raise CalibrationError("Data da rodada deve incluir fuso horário.")
    _text(report.get("next_action"), "next_action")
    provenance = report["provenance"]
    if not isinstance(provenance, dict) or any(
        not isinstance(provenance.get(key), dict) for key in ("thresholds", "hashes", "environment")
    ):
        raise CalibrationError("Proveniência incompleta na rodada salva.")
    # Rejeita NaN/Infinity também em campos que não participam da comparação.
    json.dumps(report, allow_nan=False)
    if report.get("status") == "blocked_missing_d3":
        if (
            report.get("passed") is not False
            or report.get("comparisons") != []
            or report.get("manual_annotations") is not None
            or report.get("summary") is not None
            or report.get("blocked_on") != ["D3"]
        ):
            raise CalibrationError("Bloqueio D3 contém resultados de comparação incompatíveis.")
        _text(report.get("reason"), "reason")
        return

    pairs = report["comparisons"]
    if not isinstance(pairs, list) or not pairs or not all(isinstance(p, dict) for p in pairs):
        raise CalibrationError("Rodada exige comparações por evento.")
    manual_events = tuple(
        ManualEvent(pair["tipo"], pair["hole_number"], pair["manual_t_s"])
        for pair in pairs
        if pair["manual_t_s"] is not None
    )
    automatic = [
        {"tipo": pair["tipo"], "hole_number": pair["hole_number"], "t_s": pair["automatic_t_s"]}
        for pair in pairs
        if pair["automatic_t_s"] is not None
    ]
    metadata = report["manual_annotations"]
    manual = ManualAnnotations(
        trial_id=report["trial_id"],
        observer=metadata["observer"],
        source=metadata["source"],
        delivered_on=metadata["delivered_on"],
        time_origin=report["time_origin"],
        events=manual_events,
        video_sha256=metadata.get("video_sha256"),
    )
    recalculated = compare_events(manual, automatic, kind=report["kind"])
    if pairs != recalculated["comparisons"]:
        raise CalibrationError("Erros/pareamento da rodada diferem dos tempos registrados.")
    summary = report["summary"]
    for key, expected in recalculated["summary"].items():
        if key.startswith("ignored_other_kind_"):
            _integer(summary[key], key)
        elif summary[key] != expected:
            raise CalibrationError("Resumo da rodada difere das comparações por evento.")
    issues = report.get("consistency_issues", [])
    if not isinstance(issues, list) or not all(isinstance(i, str) and i.strip() for i in issues):
        raise CalibrationError("Lista de inconsistências da rodada inválida.")
    passed = recalculated["passed"] and not issues
    expected_status = "passed" if passed else "divergence_review_required"
    if report.get("status") != expected_status or report.get("passed") is not passed:
        raise CalibrationError("Resultado da rodada não corresponde aos erros/consistência.")
    if "timing_status" in report and report["timing_status"] != recalculated["status"]:
        raise CalibrationError("Resultado temporal da rodada inconsistente.")


def load_saved_round(path: str | Path) -> dict:
    """Lê evidência local e recusa resultados internamente inconsistentes."""
    try:
        report = json.loads(
            Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=_json_object
        )
        _validate_saved_round(report)
    except CalibrationError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        raise CalibrationError(
            "Evidência inválida/incompleta; use a rodada original registrada."
        ) from exc
    return report


def save_round(
    report: Mapping[str, Any], output_dir: str | Path, *, provenance: Mapping[str, Any]
) -> tuple[Path, Path]:
    """Acrescenta UUID.json e UUID.md exclusivos; nunca sobrescreve outra rodada.

    ``provenance`` deve conter os mapeamentos ``thresholds``, ``hashes`` e
    ``environment`` produzidos pelo chamador; valores null de G3 são preservados.
    Pode conter também revisão Git, caminhos, execução e outras evidências.
    O snapshot é copiado via JSON estrito antes de qualquer escrita.
    """
    if not isinstance(provenance, Mapping) or any(
        not isinstance(provenance.get(key), Mapping)
        for key in ("thresholds", "hashes", "environment")
    ):
        raise CalibrationError("Proveniência exige os objetos thresholds, hashes e environment.")
    if report.get("status") not in {"passed", "divergence_review_required", "blocked_missing_d3"}:
        raise CalibrationError("Estado de rodada inválido.")
    if report.get("passed") is not (report["status"] == "passed"):
        raise CalibrationError("Resultado numérico inconsistente com o estado da rodada.")
    round_id = str(uuid.uuid4())
    snapshot = dict(report) | {
        "round_id": round_id,
        "created_at": datetime.now(UTC).isoformat(),
        "provenance": dict(provenance),
        "client_approval": False,
    }
    try:
        payload = json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        snapshot = json.loads(payload)
        _validate_saved_round(snapshot)
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError) as exc:
        raise CalibrationError(
            "Rodada/proveniência deve conter dados JSON finitos e comparação consistente."
        ) from exc
    markdown = render_evidence(snapshot)
    folder = Path(output_dir)
    json_path, markdown_path = folder / f"{round_id}.json", folder / f"{round_id}.md"
    if json_path.exists() or markdown_path.exists():
        raise CalibrationError("UUID de rodada já existe; nenhuma evidência foi sobrescrita.")
    folder.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        for path, content in ((json_path, payload), (markdown_path, markdown)):
            with path.open("x", encoding="utf-8") as stream:
                created.append(path)
                stream.write(content)
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return json_path, markdown_path
