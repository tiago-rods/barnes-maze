"""Concordância da classificação automática com o observador: kappa de Cohen (US-21).

Puro, sem banco: lê o CSV de rótulos manuais de estratégia, separa a amostra em
calibração e avaliação (RN05), e compara os rótulos manuais com os automáticos
que a CLI lê de `trial_results` (US-20) — kappa de Cohen (scikit-learn) e matriz
de confusão por categoria (RN02).

O critério de aceite **kappa ≥ 0,70** (RN03) é constante do card, não um limiar
operacional do laboratório, por isso fica no código e não em `configs/default.yaml`
— mesmo raciocínio do r ≥ 0,95 da US-18 (`barnes.metrics.validation`).

Ajuste dos limiares (RN04) é manual e explícito: editar a seção `estrategia` do
YAML, reexecutar `barnes strategy classify` e registrar uma nova rodada sobre
`calibracao`. Não há otimizador: a regra da US-20 continua auditável (RN01 dela).

Enquanto não houver rótulos de um observador humano (`docs/decisoes-sem-
laboratorio.md` §5.1), a rodada é registrada como bloqueada; o ferramental é
coberto por teste com rótulos sintéticos, nunca citado como validação real.
"""

from __future__ import annotations

import csv
import json
import warnings
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from math import isfinite
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.exceptions import UndefinedMetricWarning
from sklearn.metrics import cohen_kappa_score, confusion_matrix

from barnes.strategy.classification import SearchStrategy

KAPPA_THRESHOLD = 0.70
MIN_PAIRS = 3
# Ordem fixa das linhas/colunas da matriz de confusão (RN02).
CATEGORIES: tuple[SearchStrategy, ...] = (
    SearchStrategy.SPATIAL,
    SearchStrategy.SERIAL,
    SearchStrategy.RANDOM,
)
SUBSETS = ("calibracao", "avaliacao")
MANUAL_COLUMNS = ("trial_id", "estrategia_manual", "observador", "data")
PARTITION_SCHEMA_VERSION = 1

_ALIASES = {
    "spatial": SearchStrategy.SPATIAL,
    "espacial": SearchStrategy.SPATIAL,
    "serial": SearchStrategy.SERIAL,
    "random": SearchStrategy.RANDOM,
    "aleatoria": SearchStrategy.RANDOM,
    "aleatória": SearchStrategy.RANDOM,
}


class ManualLabelError(ValueError):
    """CSV de rótulos manuais ausente, fora do formato ou com valores inválidos."""


class PartitionError(ValueError):
    """Partição calibração/avaliação inválida, inconsistente ou de outra anotação."""


class AgreementError(ValueError):
    """Kappa não calculável (poucos pares, kappa indefinido, subconjunto inválido)."""


def parse_strategy_label(value: str) -> SearchStrategy:
    """Normaliza um rótulo manual em pt ou en (`espacial|spatial`, ...)."""
    key = (value or "").strip().lower()
    if key not in _ALIASES:
        opcoes = ", ".join(sorted(_ALIASES))
        raise ManualLabelError(f"Estratégia desconhecida {value!r}; use uma de: {opcoes}.")
    return _ALIASES[key]


def _check_subset(subconjunto: str) -> str:
    if subconjunto not in SUBSETS:
        raise AgreementError(f"Subconjunto {subconjunto!r} inválido; use {' ou '.join(SUBSETS)}.")
    return subconjunto


@dataclass(frozen=True)
class ManualLabel:
    """Estratégia atribuída por um observador a um trial."""

    trial_id: int
    estrategia: SearchStrategy
    observador: str
    data: str


def load_manual_labels(path: str | Path) -> tuple[ManualLabel, ...]:
    """Lê o CSV `trial_id,estrategia_manual,observador,data`.

    Raises:
        ManualLabelError: Arquivo ausente, colunas faltando, trial repetido,
            id não inteiro ou estratégia desconhecida.
    """
    path = Path(path)
    if not path.is_file():
        raise ManualLabelError(f"Rótulos manuais não encontrados: {path}")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing = [c for c in MANUAL_COLUMNS if c not in (reader.fieldnames or ())]
        if missing:
            raise ManualLabelError(
                f"{path}: faltam as colunas {', '.join(missing)} "
                f"(esperado: {','.join(MANUAL_COLUMNS)})."
            )
        labels: list[ManualLabel] = []
        seen: set[int] = set()
        for row in reader:
            line = reader.line_num
            try:
                trial_id = int(row["trial_id"])
            except (TypeError, ValueError) as exc:
                raise ManualLabelError(f"{path}, linha {line}: trial_id não inteiro.") from exc
            if trial_id < 1:
                raise ManualLabelError(f"{path}, linha {line}: trial_id deve ser >= 1.")
            try:
                estrategia = parse_strategy_label(row["estrategia_manual"])
            except ManualLabelError as exc:
                raise ManualLabelError(f"{path}, linha {line}: {exc}") from exc
            if trial_id in seen:
                raise ManualLabelError(f"{path}, linha {line}: trial {trial_id} repetido.")
            seen.add(trial_id)
            labels.append(
                ManualLabel(
                    trial_id=trial_id,
                    estrategia=estrategia,
                    observador=(row["observador"] or "").strip(),
                    data=(row["data"] or "").strip(),
                )
            )
    if not labels:
        raise ManualLabelError(f"{path}: nenhum rótulo manual.")
    return tuple(labels)


@dataclass(frozen=True)
class Partition:
    """Separação fixa da amostra anotada em calibração e avaliação (RN05).

    Attributes:
        seed: Semente do sorteio.
        frac_avaliacao: Fração pedida para avaliação, por categoria manual.
        manual_sha256: Hash do CSV de rótulos de onde a partição saiu; outra
            anotação exige outra partição.
        calibracao: Trials usados para ajustar limiares.
        avaliacao: Trials reservados ao kappa final — nunca usados no ajuste.
    """

    seed: int
    frac_avaliacao: float
    manual_sha256: str
    calibracao: tuple[int, ...]
    avaliacao: tuple[int, ...]

    def __post_init__(self) -> None:
        overlap = set(self.calibracao) & set(self.avaliacao)
        if overlap:
            raise PartitionError(
                "Trials nos dois subconjuntos: " + ", ".join(map(str, sorted(overlap))) + "."
            )
        if not self.calibracao or not self.avaliacao:
            raise PartitionError(
                "Calibração e avaliação precisam ter ao menos um trial cada; "
                "ajuste --frac-avaliacao ou anote mais trials."
            )

    def subset(self, subconjunto: str) -> tuple[int, ...]:
        return self.calibracao if _check_subset(subconjunto) == "calibracao" else self.avaliacao

    def as_record(self) -> dict[str, Any]:
        return {"schema_version": PARTITION_SCHEMA_VERSION, **asdict(self)}


def split_sample(
    labels: Iterable[ManualLabel], *, frac_avaliacao: float, seed: int, manual_sha256: str
) -> Partition:
    """Sorteia a partição, estratificada pela estratégia manual e determinística.

    Em cada categoria, `round(n * frac_avaliacao)` trials vão para avaliação; o
    resto, para calibração. A mesma anotação com a mesma semente dá sempre a
    mesma partição.

    Raises:
        PartitionError: Fração fora de (0, 1) ou um dos lados vazio.
    """
    if isinstance(frac_avaliacao, bool) or not 0 < frac_avaliacao < 1:
        raise PartitionError("frac_avaliacao deve estar entre 0 e 1 (exclusivo).")
    rng = np.random.default_rng(seed)
    labels = tuple(labels)
    calibracao: list[int] = []
    avaliacao: list[int] = []
    for categoria in CATEGORIES:
        ids = sorted(label.trial_id for label in labels if label.estrategia == categoria)
        shuffled = [ids[i] for i in rng.permutation(len(ids))]
        n_avaliacao = round(len(ids) * frac_avaliacao)
        avaliacao += shuffled[:n_avaliacao]
        calibracao += shuffled[n_avaliacao:]
    return Partition(
        seed=seed,
        frac_avaliacao=float(frac_avaliacao),
        manual_sha256=manual_sha256,
        calibracao=tuple(sorted(calibracao)),
        avaliacao=tuple(sorted(avaliacao)),
    )


def write_partition(path: str | Path, partition: Partition) -> Path:
    """Grava a partição; nunca sobrescreve uma existente (RN05).

    Raises:
        PartitionError: Já existe uma partição em `path`.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(partition.as_record(), stream, indent=2, ensure_ascii=False)
    except FileExistsError as exc:
        raise PartitionError(
            f"Já existe uma partição em {path}; regerá-la misturaria trials de calibração "
            "e de avaliação. Use outro caminho só para uma anotação nova."
        ) from exc
    return path


def load_partition(path: str | Path, *, manual_sha256: str) -> Partition:
    """Lê a partição e confere que veio do mesmo CSV de rótulos.

    Raises:
        PartitionError: Arquivo ausente, formato inválido ou hash da anotação
            diferente (a anotação mudou depois da partição).
    """
    path = Path(path)
    if not path.is_file():
        raise PartitionError(
            f"Partição não encontrada: {path}. Crie com `barnes strategy split` antes."
        )
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("schema_version") != PARTITION_SCHEMA_VERSION:
            raise PartitionError(f"{path}: versão de partição não suportada.")
        partition = Partition(
            seed=int(record["seed"]),
            frac_avaliacao=float(record["frac_avaliacao"]),
            manual_sha256=str(record["manual_sha256"]),
            calibracao=tuple(int(t) for t in record["calibracao"]),
            avaliacao=tuple(int(t) for t in record["avaliacao"]),
        )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        if isinstance(exc, PartitionError):
            raise
        raise PartitionError(f"{path}: partição em formato inválido ({exc}).") from exc
    if partition.manual_sha256 != manual_sha256:
        raise PartitionError(
            f"{path} foi criada a partir de outro CSV de rótulos (hash diferente). "
            "Uma anotação nova exige uma partição nova."
        )
    return partition


@dataclass(frozen=True)
class StrategyPair:
    """Rótulo manual e automático de um mesmo trial."""

    trial_id: int
    manual: SearchStrategy
    automatico: SearchStrategy


@dataclass(frozen=True)
class CategoryAgreement:
    """Desempenho da regra numa categoria (RN02).

    Attributes:
        sensibilidade: Acertos ÷ trials que o observador pôs na categoria;
            `None` se o observador não usou a categoria.
        precisao: Acertos ÷ trials que a regra pôs na categoria; `None` se a
            regra não usou a categoria.
    """

    categoria: str
    n_manual: int
    n_automatico: int
    acertos: int
    sensibilidade: float | None
    precisao: float | None


@dataclass(frozen=True)
class AgreementResult:
    """Resultado de uma rodada de concordância.

    Attributes:
        matriz: Matriz de confusão; linha = observador, coluna = regra, na ordem
            de `categorias`.
        categorias_ausentes: Categorias que nem observador nem regra usaram —
            ficam com zeros na matriz e são sinalizadas.
    """

    subconjunto: str
    n: int
    kappa: float
    concordancia_bruta: float
    limiar: float
    aprovado: bool
    categorias: tuple[str, ...]
    matriz: tuple[tuple[int, ...], ...]
    por_categoria: tuple[CategoryAgreement, ...]
    categorias_ausentes: tuple[str, ...]
    pares: tuple[StrategyPair, ...]
    excluidos: tuple[tuple[int, str], ...]

    def as_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["status"] = "aprovado" if self.aprovado else "reprovado"
        record["pares"] = [
            {"trial_id": p.trial_id, "manual": p.manual.value, "automatico": p.automatico.value}
            for p in self.pares
        ]
        record["excluidos"] = [{"trial_id": t, "motivo": m} for t, m in self.excluidos]
        record["declaracao"] = declaration(self.subconjunto, self.n)
        return record


def declaration(subconjunto: str, n: int) -> str:
    """O que a rodada pode e não pode afirmar (Cenário 3)."""
    if _check_subset(subconjunto) == "avaliacao":
        return (
            f"Kappa calculado sobre {n} trials do subconjunto de avaliação, que não "
            "participaram do ajuste dos limiares."
        )
    return (
        f"Rodada de calibração ({n} trials): estes trials podem ser usados para ajustar os "
        "limiares, por isso este kappa não é o resultado final."
    )


def compute_agreement(
    pairs: Iterable[StrategyPair],
    *,
    subconjunto: str,
    excluded: Iterable[tuple[int, str]] = (),
    threshold: float = KAPPA_THRESHOLD,
) -> AgreementResult:
    """Kappa de Cohen e matriz de confusão entre observador e regra (Cenários 1 e 2).

    Raises:
        AgreementError: Subconjunto inválido, menos de `MIN_PAIRS` pares, ou
            kappa indefinido (ex.: uma única categoria nos dois lados — a
            concordância esperada é 1 e o kappa não é zero nem um).
    """
    _check_subset(subconjunto)
    pairs = tuple(pairs)
    if len(pairs) < MIN_PAIRS:
        raise AgreementError(
            f"São necessários ao menos {MIN_PAIRS} trials com rótulo manual e automático; "
            f"há {len(pairs)}."
        )
    labels = [c.value for c in CATEGORIES]
    manual = [p.manual.value for p in pairs]
    auto = [p.automatico.value for p in pairs]
    with warnings.catch_warnings():
        # Kappa indefinido vira nan + aviso no sklearn; aqui vira AgreementError abaixo.
        warnings.simplefilter("ignore", RuntimeWarning)
        warnings.simplefilter("ignore", UndefinedMetricWarning)
        kappa = float(cohen_kappa_score(manual, auto, labels=labels))
    if not isfinite(kappa):
        raise AgreementError(
            "Kappa indefinido: observador e regra usaram uma única e mesma categoria, então a "
            "concordância esperada ao acaso é 1. A amostra precisa cobrir mais de uma estratégia."
        )
    matrix = confusion_matrix(manual, auto, labels=labels)
    per_category = []
    for i, categoria in enumerate(labels):
        n_manual = int(matrix[i, :].sum())
        n_auto = int(matrix[:, i].sum())
        hits = int(matrix[i, i])
        per_category.append(
            CategoryAgreement(
                categoria=categoria,
                n_manual=n_manual,
                n_automatico=n_auto,
                acertos=hits,
                sensibilidade=hits / n_manual if n_manual else None,
                precisao=hits / n_auto if n_auto else None,
            )
        )
    return AgreementResult(
        subconjunto=subconjunto,
        n=len(pairs),
        kappa=kappa,
        concordancia_bruta=float(np.trace(matrix)) / len(pairs),
        limiar=threshold,
        aprovado=kappa >= threshold,
        categorias=tuple(labels),
        matriz=tuple(tuple(int(v) for v in row) for row in matrix),
        por_categoria=tuple(per_category),
        categorias_ausentes=tuple(
            c.categoria for c in per_category if c.n_manual == 0 and c.n_automatico == 0
        ),
        pares=pairs,
        excluidos=tuple(excluded),
    )


def blocked_record(reason: str, *, subconjunto: str | None = None) -> dict[str, Any]:
    """Registro de rodada sem rótulos manuais: aceite bloqueado, nada calculado."""
    return {
        "status": "bloqueado",
        "motivo": reason,
        "subconjunto": subconjunto,
        "limiar": KAPPA_THRESHOLD,
        "proxima_acao": (
            "Obter a classificação de estratégia de um observador (D3 — "
            "docs/decisoes-sem-laboratorio.md §5.1), rodar `barnes strategy split` e "
            "repetir a rodada."
        ),
    }


def optimism_warning(
    history: Iterable[Mapping[str, Any]], *, limiares: Mapping[str, Any]
) -> str | None:
    """Aviso se o subconjunto de avaliação já foi avaliado com outros limiares.

    Avaliar, ajustar e reavaliar o mesmo subconjunto de avaliação também é ajuste
    sobre ele (RN05): o kappa final fica otimista mesmo sem usar os trials de
    calibração. Rodadas bloqueadas não contam.
    """
    previous = [
        r
        for r in history
        if r.get("subconjunto") == "avaliacao"
        and r.get("status") in ("aprovado", "reprovado")
        and r.get("limiares") != dict(limiares)
    ]
    if not previous:
        return None
    return (
        f"O subconjunto de avaliação já foi avaliado {len(previous)} vez(es) com outros "
        "limiares: se eles mudaram depois de ver aquele kappa, este resultado é otimista "
        "(RN05). Declare isso no relatório ou use uma anotação nova."
    )


def _fmt(value: float | None, spec: str) -> str:
    return "—" if value is None else format(value, spec)


def render_markdown(record: Mapping[str, Any]) -> str:
    """Relatório legível de uma rodada (aprovada, reprovada ou bloqueada)."""
    lines = ["# US-21 — concordância da classificação de estratégia com o observador", ""]
    lines.append(f"- Status: **{record['status']}**")
    lines.append(f"- Critério: kappa de Cohen ≥ {record['limiar']:.2f}")
    if record.get("subconjunto"):
        lines.append(f"- Subconjunto: {record['subconjunto']}")
    if record["status"] == "bloqueado":
        lines += [f"- Motivo: {record['motivo']}", f"- Próxima ação: {record['proxima_acao']}"]
        return "\n".join(lines) + "\n"
    lines += [
        (
            f"- n = {record['n']} trials · kappa = {record['kappa']:.4f} · "
            f"concordância bruta = {record['concordancia_bruta']:.1%}"
        ),
        f"- {record['declaracao']}",
    ]
    if record.get("aviso_otimismo"):
        lines.append(f"- **Aviso:** {record['aviso_otimismo']}")
    categorias = record["categorias"]
    lines += [
        "",
        "Matriz de confusão (linha = observador, coluna = regra):",
        "",
        "| observador \\ regra | " + " | ".join(categorias) + " |",
        "|---|" + "---:|" * len(categorias),
    ]
    lines += [
        f"| {categoria} | " + " | ".join(str(v) for v in row) + " |"
        for categoria, row in zip(categorias, record["matriz"], strict=True)
    ]
    lines += [
        "",
        "| categoria | observador | regra | acertos | sensibilidade | precisão |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    lines += [
        f"| {c['categoria']} | {c['n_manual']} | {c['n_automatico']} | {c['acertos']} | "
        f"{_fmt(c['sensibilidade'], '.1%')} | {_fmt(c['precisao'], '.1%')} |"
        for c in record["por_categoria"]
    ]
    if record["categorias_ausentes"]:
        lines += [
            "",
            "Categorias sem nenhum trial (nem observador nem regra): "
            + ", ".join(record["categorias_ausentes"])
            + ".",
        ]
    if record.get("limiares"):
        lines += ["", "Limiares da regra (US-20) nesta rodada:", ""]
        lines += [f"- `{k}`: {v}" for k, v in record["limiares"].items()]
    if record["excluidos"]:
        lines += ["", "Trials anotados fora da comparação:", ""]
        lines += [f"- {e['trial_id']}: {e['motivo']}" for e in record["excluidos"]]
    return "\n".join(lines) + "\n"


def render_history(records: Iterable[Mapping[str, Any]]) -> list[str]:
    """Uma linha por rodada, em ordem cronológica (RN04)."""
    rows = sorted(records, key=lambda r: r.get("criado_em", ""))
    lines = []
    for i, r in enumerate(rows, start=1):
        kappa = "—" if r.get("kappa") is None else f"{r['kappa']:.4f}"
        lines.append(
            f"{i:>3}. {r.get('criado_em', '?')}  {r.get('subconjunto') or '—':<10}  "
            f"{r['status']:<9}  kappa = {kappa}  n = {r.get('n', '—')}"
        )
        if r.get("aviso_otimismo"):
            lines.append(f"     aviso: {r['aviso_otimismo']}")
    return lines
