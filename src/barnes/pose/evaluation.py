"""Avaliação de pose no teste congelado, global e por região (US-08).

O corpo é a distância euclidiana entre focinho e base da cauda **anotados**
em cada quadro. Cada erro é dividido pelo corpo daquele mesmo quadro antes
de calcular a mediana; uma mediana em pixels dividida pelo corpo mediano
não é equivalente. O limite de 0,5 vem expressamente de US-08 RN01.

Predições ausentes/não finitas recebem erro infinito no cálculo e também
reprovam a cobertura, mesmo quando poucas ausências não mudam a mediana.
Infinito é representado por null + median_unbounded no JSON, nunca NaN.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from statistics import median

from barnes.geometry.holes import MazeGeometry
from barnes.pose.annotations import KEYPOINTS, AnnotatedFrame
from barnes.pose.regions import Region, RegionParams, classify_region
from barnes.pose.split import SETS, ManifestRow, check_no_leakage, summarize

MAX_BODY_FRACTION = 0.5


class EvaluationError(ValueError):
    """A avaliação não pode ser interpretada com os dados fornecidos."""


def _indexed(frames: list[AnnotatedFrame], source: str) -> dict[tuple[str, int], AnnotatedFrame]:
    indexed = {}
    for frame in frames:
        key = (frame.trial, frame.frame_index)
        if (
            not frame.trial
            or not isinstance(frame.frame_index, int)
            or isinstance(frame.frame_index, bool)
            or frame.frame_index < 0
        ):
            raise EvaluationError(f"{source}: trial/quadro inválido: {key}.")
        if key in indexed:
            raise EvaluationError(f"{source}: quadro duplicado: {key}.")
        indexed[key] = frame
    return indexed


def _point(point: tuple[float, float], context: str) -> tuple[float, float]:
    try:
        if len(point) != 2:
            raise ValueError
        return float(point[0]), float(point[1])
    except (ValueError, TypeError, OverflowError) as exc:
        raise EvaluationError(f"{context}: cada ponto exige duas coordenadas numéricas.") from exc


def _validate_inputs(
    annotations: list[AnnotatedFrame],
    predictions: list[AnnotatedFrame],
    manifest: list[ManifestRow],
) -> tuple[dict, dict, dict]:
    truth = _indexed(annotations, "Anotações")
    predicted = _indexed(predictions, "Predições")
    if not truth:
        raise EvaluationError("O conjunto anotado está vazio.")
    assignment = {}
    for row in manifest:
        key = (row.trial, row.frame_index)
        if (
            not row.trial
            or not isinstance(row.frame_index, int)
            or isinstance(row.frame_index, bool)
            or row.frame_index < 0
        ):
            raise EvaluationError(f"Divisão: trial/quadro inválido: {key}.")
        if row.subset not in SETS:
            raise EvaluationError(f"Conjunto inválido na divisão: {row.subset}.")
        if key in assignment:
            raise EvaluationError(f"Divisão: quadro duplicado: {key}.")
        assignment[key] = row.subset
    check_no_leakage(manifest)
    if set(assignment.values()) != set(SETS):
        raise EvaluationError("A divisão deve conter treino, validacao e teste não vazios.")
    if truth.keys() != assignment.keys():
        absent = sorted(truth.keys() - assignment.keys())
        extra = sorted(assignment.keys() - truth.keys())
        raise EvaluationError(
            "Anotações e divisão devem conter exatamente os mesmos quadros; "
            f"sem divisão: {absent[:5]}; sem anotação: {extra[:5]}."
        )
    unknown = predicted.keys() - truth.keys()
    if unknown:
        raise EvaluationError(f"Predições de quadros fora da divisão: {sorted(unknown)[:5]}.")
    for key, frame in truth.items():
        if len(frame.points) != len(KEYPOINTS):
            raise EvaluationError(f"Anotação {key}: são obrigatórios os três pontos.")
        for name, point in zip(KEYPOINTS, frame.points, strict=True):
            if not all(math.isfinite(v) for v in _point(point, f"Anotação {key}/{name}")):
                raise EvaluationError(f"Anotação {key}/{name}: coordenada não finita.")
    return truth, predicted, assignment


def _statistics(errors: list[tuple[float, float]]) -> dict:
    count = len(errors)
    missing = sum(not math.isfinite(px) or not math.isfinite(body) for px, body in errors)
    px = median(error[0] for error in errors) if count else None
    body = median(error[1] for error in errors) if count else None
    unbounded = body is not None and not math.isfinite(body)
    return {
        "samples": count,
        "valid_samples": count - missing,
        "missing_predictions": missing,
        "median_error_px": px if px is not None and math.isfinite(px) else None,
        "median_error_body_fraction": body if body is not None and math.isfinite(body) else None,
        "median_unbounded": unbounded,
        "passed": bool(count and not missing and body < MAX_BODY_FRACTION),
    }


def _summarize_frames(frames: list[dict]) -> dict:
    by_keypoint = {}
    aggregate = []
    for name in KEYPOINTS:
        errors = [
            (
                frame["keypoints"][name]["error_px"]
                if frame["keypoints"][name]["error_px"] is not None
                else math.inf,
                frame["keypoints"][name]["error_body_fraction"]
                if frame["keypoints"][name]["error_body_fraction"] is not None
                else math.inf,
            )
            for frame in frames
        ]
        by_keypoint[name] = _statistics(errors)
        aggregate.extend(errors)
    summary = _statistics(aggregate)
    return {
        "frames": len(frames),
        "aggregate": summary,
        "by_keypoint": by_keypoint,
        "passed": summary["passed"] and all(item["passed"] for item in by_keypoint.values()),
    }


def evaluate_pose(
    annotations: list[AnnotatedFrame],
    predictions: list[AnnotatedFrame],
    manifest: list[ManifestRow],
    geometries: Mapping[str, MazeGeometry],
    params: RegionParams,
) -> dict:
    """Compara os três pontos usando somente os quadros reservados para teste.

    Args:
        annotations: Todas as anotações de treino, validação e teste.
        predictions: Predições internas, na ordem de ``KEYPOINTS``. Quadros
            conhecidos de treino/validação são ignorados e contados no relatório.
            Quadros desconhecidos ou duplicados são recusados. Um quadro ausente,
            ponto ausente ou coordenada não finita conta como falha de predição.
        manifest: Divisão completa, sem vazamento entre trials.
        geometries: Geometria original de cada trial de teste, indexada por trial.
        params: Fronteiras do protocolo US-06, também registradas no relatório.

    Returns:
        Relatório serializável como JSON. ``accepted`` é somente o aceite da
        qualidade; a validação offline na máquina do laboratório é independente.
        O relatório exige cobertura e mediana < 0,5 por ponto e agregada em
        todas as regiões, além do global. Região ausente não pode ser aprovada.

    Raises:
        EvaluationError: Divisão/alinhamento/anotação/geometria inválidos, ou
            comprimento corporal zero em um quadro de teste.
        SplitLeakageError: Um trial aparece em mais de um subconjunto.
    """
    truth, predicted, assignment = _validate_inputs(annotations, predictions, manifest)
    if not all(math.isfinite(value) for value in asdict(params).values()):
        raise EvaluationError("As fronteiras de região devem ser finitas.")
    test_keys = sorted(key for key, subset in assignment.items() if subset == "teste")
    frame_errors = []
    for key in test_keys:
        actual = truth[key]
        geometry = geometries.get(actual.trial)
        if geometry is None:
            raise EvaluationError(f"Geometria ausente para o trial de teste {actual.trial}.")
        body_px = math.dist(actual.point("focinho"), actual.point("base_cauda"))
        if not math.isfinite(body_px) or body_px <= 0:
            raise EvaluationError(f"Anotação {key}: comprimento corporal deve ser finito e > 0.")
        region = classify_region(*actual.point("centro_corpo"), geometry, params)
        estimate = predicted.get(key)
        if estimate is not None and len(estimate.points) > len(KEYPOINTS):
            raise EvaluationError(f"Predição {key}: esqueleto com mais de três pontos.")
        point_errors = {}
        for index, name in enumerate(KEYPOINTS):
            point = (
                _point(estimate.points[index], f"Predição {key}/{name}")
                if estimate is not None and index < len(estimate.points)
                else (math.nan, math.nan)
            )
            error_px = math.dist(actual.points[index], point)
            normalized = error_px / body_px
            valid = math.isfinite(error_px) and math.isfinite(normalized)
            point_errors[name] = {
                "error_px": error_px if valid else None,
                "error_body_fraction": normalized if valid else None,
                "missing_prediction": not valid,
            }
        frame_errors.append(
            {
                "trial": actual.trial,
                "frame_index": actual.frame_index,
                "region": region.value,
                "body_length_px": body_px,
                "keypoints": point_errors,
            }
        )
    global_metrics = _summarize_frames(frame_errors)
    regions = {
        region.value: _summarize_frames([f for f in frame_errors if f["region"] == region.value])
        for region in Region
    }
    accepted = global_metrics["passed"] and all(region["passed"] for region in regions.values())
    held_out_trials = sorted({key[0] for key in test_keys})
    follow_up = None
    if not regions[Region.BORDA.value]["passed"]:
        follow_up = {
            "story": "US-06",
            "status": "pending_local",
            "title": "Nova rodada de anotação com foco na borda",
            "risk": "perda de pose junto à borda",
            "focus_region": Region.BORDA.value,
            "reason": (
                "Teste sem quadros de borda."
                if not regions[Region.BORDA.value]["frames"]
                else "Borda reprovada por mediana >= 0,5 corpo ou predições ausentes."
            ),
            "frozen_test_trials": held_out_trials,
            "instructions": [
                "Amostrar novos trials com foco em borda e anotar os três pontos no SLEAP.",
                "Manter os trials de teste congelados, sem reutilizá-los em treino/validação.",
                "Registrar nova versão do conjunto e do modelo e repetir a avaliação.",
                "Manter os dados locais; esta solicitação não cria ticket nem envia mensagens.",
            ],
        }
    return {
        "schema_version": 1,
        "accepted": accepted,
        "acceptance_scope": "qualidade no teste; validação offline é registrada separadamente",
        "protocol": {
            "threshold_body_fraction": MAX_BODY_FRACTION,
            "comparison": "strictly_less_than",
            "body_definition": "distância euclidiana focinho-base_cauda anotados em cada quadro",
            "normalization": "erro de cada ponto dividido pelo corpo do mesmo quadro",
            "region_reference": "centro_corpo anotado e geometria do próprio trial",
            "regions": asdict(params),
            "missing_prediction_policy": "erro infinito e reprovação de cobertura",
            "acceptance": "global e todas as regiões; agregado e cada ponto; cobertura completa",
        },
        "split": {
            subset: {"trials": counts[0], "frames": counts[1]}
            for subset, counts in summarize(manifest).items()
        },
        "test_trials": held_out_trials,
        "test_geometries": {
            trial: {
                **asdict(geometries[trial]),
                "holes": [asdict(hole) for hole in geometries[trial].holes],
            }
            for trial in held_out_trials
        },
        "ignored_non_test_predictions": sum(assignment[key] != "teste" for key in predicted),
        "global": global_metrics,
        "regions": regions,
        "frame_errors": frame_errors,
        "follow_up": follow_up,
    }


def _display(value: float | None, unbounded: bool) -> str:
    return "infinito" if unbounded else ("sem amostras" if value is None else f"{value:.4f}")


def _report_markdown(report: dict) -> str:
    status = "APROVADO" if report["accepted"] else "REPROVADO"
    lines = [
        f"# US-08 — avaliação de pose: {status}",
        "",
        "Aceite de qualidade no teste; a validação offline é registrada separadamente.",
        (
            "O corpo é a distância focinho–base da cauda anotada em cada quadro. "
            "A normalização precede a mediana. Limite estrito: erro < 0,5 corpo."
        ),
        (
            "Predições ausentes/não finitas contam como infinito e reprovam a cobertura. "
            "Regiões sem amostras reprovam. Classificação pelo centro do corpo anotado."
        ),
        "",
        "| Região | Ponto | Amostras | Ausentes | Mediana (px) | Mediana (corpos) | Aceite |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for name, region in {"global": report["global"], **report["regions"]}.items():
        for point, metrics in {"todos": region["aggregate"], **region["by_keypoint"]}.items():
            px = _display(metrics["median_error_px"], metrics["median_unbounded"])
            body = _display(metrics["median_error_body_fraction"], metrics["median_unbounded"])
            passed = "sim" if metrics["passed"] else "não"
            lines.append(
                f"| {name} | {point} | {metrics['samples']} | {metrics['missing_predictions']} "
                f"| {px} | {body} | {passed} |"
            )
    lines.extend(
        [
            "",
            f"Predições de treino/validação ignoradas: {report['ignored_non_test_predictions']}.",
            "O JSON anexo contém protocolo, divisão e erros individuais para auditoria.",
        ]
    )
    if report["follow_up"]:
        lines.extend(["", "Borda reprovada: solicitação local US-06 em `us06-borda.md`."])
    return "\n".join(lines) + "\n"


def write_evaluation_report(report: dict, output_dir: Path) -> dict[str, Path]:
    """Grava JSON/Markdown e solicitação local de anotação quando a borda reprova.

    Não usa rede ou banco. Recusa sobrescrita para preservar relatórios prévios;
    use um diretório por avaliação/modelo/conjunto.
    """
    output_dir = Path(output_dir)
    paths = {
        "evaluation_json": output_dir / "avaliacao.json",
        "evaluation_markdown": output_dir / "avaliacao.md",
    }
    contents = {
        "evaluation_json": json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        "evaluation_markdown": _report_markdown(report),
    }
    follow_up = report.get("follow_up")
    if follow_up:
        paths.update(
            {
                "annotation_request_json": output_dir / "us06-borda.json",
                "annotation_request_markdown": output_dir / "us06-borda.md",
            }
        )
        contents["annotation_request_json"] = (
            json.dumps(follow_up, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        )
        contents["annotation_request_markdown"] = "\n".join(
            [
                f"# US-06 — {follow_up['title']}",
                "",
                "Estado: pendente local; nenhum ticket externo foi criado.",
                f"Risco: {follow_up['risk']}.",
                f"Motivo: {follow_up['reason']}",
                "",
                *[f"- {instruction}" for instruction in follow_up["instructions"]],
                "",
                "Trials de teste congelados: " + ", ".join(follow_up["frozen_test_trials"]),
                "",
            ]
        )
    for path in paths.values():
        if path.exists():
            raise EvaluationError(f"Relatório já existe: {path}. Use outro diretório de saída.")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, path in paths.items():
        with path.open("x", encoding="utf-8") as file:
            file.write(contents[name])
    return paths
