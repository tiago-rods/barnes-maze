"""Catálogo de trials: animal, sessão, situação de processamento e cobertura de pose (US-27 RN03).

Funções puras sobre uma conexão — sem Typer nem impressão — para alimentar a
CLI hoje e outra interface depois (SCRUM-151). A situação é **derivada** do
que existe no banco, nunca gravada (`trials.status`, da 0001, não é usado),
no mesmo espírito da obsolescência da US-02:

- ``sem_recorte``: trial sem intervalo útil (US-03) — nada pode ser processado;
- ``carregado``: com intervalo, ainda sem inferência de pose nem métricas;
- ``pose_inferida``: há inferência de pose concluída, ainda sem métricas;
- ``processado``: há métricas e a mais recente usa a escala atual da montagem;
- ``obsoleto``: há métricas, mas a escala da montagem mudou depois (US-02 RN05).

A conferência do arquivo de vídeo (US-27 RN04) é opcional e separada da
consulta: com `verify="size"` só existência e tamanho (rápido), com
`verify="hash"` o conteúdo inteiro de cada vídeo é relido.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

import psycopg

from barnes.io.video import FileCheck, verify_video_file


class Situation(StrEnum):
    """Situação de processamento de um trial, derivada na leitura."""

    SEM_RECORTE = "sem_recorte"
    CARREGADO = "carregado"
    POSE_INFERIDA = "pose_inferida"
    PROCESSADO = "processado"
    OBSOLETO = "obsoleto"


@dataclass(frozen=True)
class CatalogEntry:
    """Uma linha do catálogo.

    Attributes:
        trial_id: Id do trial.
        experiment_id: Experimento do trial.
        animal: Nome do animal (`subjects.name`), ou `None` se não cadastrado.
        sessao: Número da sessão (`day_number`, ver VIEW `sessao`).
        fase: habituation | acquisition | probe.
        trial_no_dia: Ordem do trial dentro da sessão.
        filename: Nome do arquivo catalogado.
        filepath: Caminho catalogado do vídeo.
        content_hash: Identidade do vídeo (US-01 RN05).
        situacao: Situação de processamento derivada.
        cobertura_pose: Fração de quadros com pose válida (US-10), ou `None`.
        execucao_id: Execução da métrica mais recente, se houver.
        calculado_em: Quando a métrica mais recente foi calculada.
        arquivo: Resultado da conferência do vídeo, se pedida.
    """

    trial_id: int
    experiment_id: int
    animal: str | None
    sessao: int
    fase: str
    trial_no_dia: int
    filename: str
    filepath: Path
    content_hash: str
    situacao: Situation
    cobertura_pose: float | None
    execucao_id: int | None
    calculado_em: datetime | None
    file_size_bytes: int | None = None
    arquivo: FileCheck | None = None

    @property
    def diverges(self) -> bool:
        """True se a conferência do vídeo achou arquivo movido, alterado ou ausente."""
        return self.arquivo is not None and self.arquivo.diverges


_QUERY = """
    SELECT t.id, t.experiment_id, s.name, t.day_number, t.phase, t.trial_number_in_day,
           t.filename, t.filepath, t.content_hash, t.file_size_bytes,
           t.start_time_seconds IS NULL OR t.end_time_seconds IS NULL AS sem_recorte,
           EXISTS (
               SELECT 1 FROM execucao e
               WHERE e.trial_id = t.id AND e.kind = 'inferencia' AND e.status = 'concluido'
           ) AS pose_inferida,
           t.cobertura_pose,
           ultima.execucao_id, ultima.calculated_at,
           (ultima.id IS NOT NULL AND (
               ultima.calculated_at IS NULL
               OR ultima.calculated_at::date < mc.calibration_date
               OR ultima.px_per_10cm_used IS DISTINCT FROM mc.px_per_10cm
           )) AS obsoleto
    FROM trials t
    JOIN maze_configs mc ON mc.id = t.maze_config_id
    LEFT JOIN subjects s ON s.experiment_id = t.experiment_id
    LEFT JOIN LATERAL (
        SELECT tr.id, tr.execucao_id, tr.calculated_at, tr.px_per_10cm_used
        FROM trial_results tr
        WHERE tr.trial_id = t.id
        ORDER BY tr.calculated_at DESC NULLS LAST, tr.id DESC
        LIMIT 1
    ) ultima ON TRUE
"""


def _situation(
    *, sem_recorte: bool, pose_inferida: bool, has_metrics: bool, obsoleto: bool
) -> Situation:
    if has_metrics:
        return Situation.OBSOLETO if obsoleto else Situation.PROCESSADO
    if sem_recorte:
        return Situation.SEM_RECORTE
    return Situation.POSE_INFERIDA if pose_inferida else Situation.CARREGADO


def list_catalog(
    conn: psycopg.Connection,
    *,
    experiment_id: int | None = None,
    trial_ids: Sequence[int] | None = None,
    verify: Literal["size", "hash"] | None = None,
    search_dirs: Sequence[str | Path] = (),
) -> list[CatalogEntry]:
    """Lista o catálogo de trials, opcionalmente conferindo os vídeos (RN03/RN04).

    Args:
        conn: Conexão psycopg aberta (só leitura; não comita nada).
        experiment_id: Restringe a um experimento.
        trial_ids: Restringe a estes trials.
        verify: `None` não toca nos arquivos; `"size"` confere existência e
            tamanho; `"hash"` relê cada vídeo e compara o conteúdo.
        search_dirs: Pastas extras onde procurar vídeos movidos.

    Returns:
        As linhas, ordenadas por experimento, sessão, fase e ordem no dia.
    """
    conditions, values = [], []
    if experiment_id is not None:
        conditions.append("t.experiment_id = %s")
        values.append(experiment_id)
    if trial_ids is not None:
        conditions.append("t.id = ANY(%s)")
        values.append(list(trial_ids))
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    order = " ORDER BY t.experiment_id, t.day_number, t.phase, t.trial_number_in_day, t.id"
    with conn.cursor() as cur:
        cur.execute(_QUERY + where + order, values)
        rows = cur.fetchall()

    entries = []
    for row in rows:
        (
            trial_id, exp_id, animal, day, phase, number, filename, filepath, digest, size,
            sem_recorte, pose_inferida, cobertura, execucao_id, calculado_em, obsoleto,
        ) = row
        entries.append(
            CatalogEntry(
                trial_id=trial_id,
                experiment_id=exp_id,
                animal=animal,
                sessao=day,
                fase=phase,
                trial_no_dia=number,
                filename=filename,
                filepath=Path(filepath),
                content_hash=digest,
                situacao=_situation(
                    sem_recorte=sem_recorte,
                    pose_inferida=pose_inferida,
                    has_metrics=execucao_id is not None,
                    obsoleto=obsoleto,
                ),
                cobertura_pose=cobertura,
                execucao_id=execucao_id,
                calculado_em=calculado_em,
                file_size_bytes=size,
            )
        )
    if verify is None:
        return entries
    return [check_entry_file(entry, verify=verify, search_dirs=search_dirs) for entry in entries]


def check_entry_file(
    entry: CatalogEntry,
    *,
    verify: Literal["size", "hash"] = "hash",
    search_dirs: Sequence[str | Path] = (),
) -> CatalogEntry:
    """Confere o vídeo de uma linha do catálogo contra o hash/tamanho catalogados (RN04)."""
    check = verify_video_file(
        entry.filepath,
        entry.content_hash,
        expected_size=entry.file_size_bytes,
        verify_hash=verify == "hash",
        search_dirs=search_dirs,
    )
    return replace(entry, arquivo=check)
