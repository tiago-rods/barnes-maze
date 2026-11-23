"""Distribuição de estratégias de busca entre sessões (ou grupos): qui-quadrado × Fisher (US-23).

Puro, sem banco e sem vídeo. A entrada é mínima e desacoplada da US-20 (classificação
de estratégia, ainda não implementada): uma lista de `StrategyObservation`, uma por
trial, com o rótulo da linha (sessão = `trials.day_number`, ou grupo experimental) e a
estratégia classificada. Quando a US-20 existir, quem lê `trial_results.search_strategy`
monta essa lista; este módulo não classifica nada.

Etapas (RN01-RN04):

1. `build_contingency_table`: tabela linha × estratégia com **todas** as categorias,
   na ordem dada. Categoria sem nenhum trial aparece com zeros e é sinalizada, nunca
   omitida (Cenário 3); sessão sem trial classificado idem. Trials sem classificação
   (`estrategia = None`) ficam fora da tabela, contados e avisados.
2. `run_independence_test`: escolhe o teste pelas **frequências esperadas** (RN02):
   se alguma célula esperada fica abaixo de `estatistica.frequencia_esperada_minima`
   (`configs/default.yaml`, `null` até a conversa com o estatístico), aplica o exato de
   Fisher; senão, qui-quadrado de independência. A justificativa vai no resultado.
3. O resultado traz tabela, teste, estatística, valor-p e justificativa (RN03), em
   `as_record()` (JSON) e `render_markdown()`. Um valor-p alto é resultado válido (RN05).

Decisões técnicas (registradas em `docs/definicoes-metricas.md`, "Distribuição de
estratégias"):

- Linhas e colunas **inteiramente zeradas** ficam na tabela reportada, mas fora do
  teste: frequência esperada zero torna o qui-quadrado indefinido (0/0), e uma margem
  zero não muda a distribuição condicional do Fisher. Sem isso, toda categoria ausente
  forçaria o Fisher, e a escolha deixaria de depender do tamanho da amostra.
- **Fisher 2×2**: `scipy.stats.fisher_exact` clássico, exato e determinístico
  (estatística = razão de chances).
- **Fisher R×C**: `scipy.stats.fisher_exact` com `method=MonteCarloMethod` (SciPy
  >= 1.15). A estatística é a probabilidade da tabela observada sob independência com
  margens fixas, e o valor-p é estimado por Monte Carlo sobre `scipy.stats.random_table`.
  Sem `method`, o SciPy também usa Monte Carlo, mas com semente aleatória, e o mesmo
  dado daria valores-p diferentes. Por isso a semente e o número de reamostragens são
  fixos (`MONTE_CARLO_*`) e saem no resultado. A enumeração exata R×C não existe no
  SciPy e pode ser inviável com 4 sessões × 3 estratégias × dezenas de trials.
- **Qui-quadrado**: `scipy.stats.chi2_contingency`. A correção de continuidade de
  Yates (padrão do SciPy) só atua com 1 grau de liberdade (2×2); o uso é registrado.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from scipy import stats
from scipy.stats.contingency import expected_freq

DEFAULT_CONFIG_PATH = Path("configs/default.yaml")

# Categorias de estratégia: as três de Harrison et al. (2006), decisão da equipe
# (`docs/decisoes-sem-laboratorio.md` §10), com os códigos que o banco aceita em
# `trial_results.search_strategy` (CHECK da migração 0001). Ordem = ordem das colunas.
DEFAULT_STRATEGIES = ("spatial", "serial", "random")

# Monte Carlo do Fisher R×C: parâmetros do método numérico, não limiares do
# laboratório (como a tolerância de `metrics.efficiency`). Com 99.999 reamostragens, o
# erro-padrão do valor-p em torno de 0,05 é ~0,0007. A semente fixa torna o resultado
# reprodutível. Os dois saem no resultado.
MONTE_CARLO_REAMOSTRAGENS = 99_999
MONTE_CARLO_SEMENTE = 0


# Rótulo legível de cada dimensão, para avisos e relatórios.
_DIMENSION_LABEL = {"sessao": "sessão", "grupo": "grupo"}


def _label(dimensao: str) -> str:
    return _DIMENSION_LABEL.get(dimensao, dimensao)


class StatsConfigError(ValueError):
    """`estatistica.frequencia_esperada_minima` ausente ou inválida (US-23 RN02)."""


def load_min_expected_frequency(path: str | Path = DEFAULT_CONFIG_PATH) -> float:
    """Lê o limite de frequência esperada que escolhe entre qui-quadrado e Fisher (RN02).

    Raises:
        StatsConfigError: Arquivo ou seção ausente, valor vazio (`null`), não numérico
            ou não positivo. O valor de produção fica `null` até a conversa com o
            estatístico; sem ele, o teste não é escolhido. Este erro é esperado até
            lá, não um defeito.
    """
    path = Path(path)
    if not path.is_file():
        raise StatsConfigError(f"Arquivo de configuração não encontrado: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    section = data.get("estatistica") if isinstance(data, Mapping) else None
    if not isinstance(section, Mapping):
        raise StatsConfigError(f"Seção 'estatistica' ausente em {path}.")
    value = section.get("frequencia_esperada_minima")
    if value is None:
        raise StatsConfigError(
            "'estatistica.frequencia_esperada_minima' está vazio em configs/default.yaml: o "
            "limite que escolhe entre qui-quadrado e exato de Fisher (US-23 RN02) ainda não "
            "foi decidido (convenção usual: 5, Cochran). A tabela de contingência pode ser "
            "montada, mas o teste não é escolhido sem esse valor."
        )
    if isinstance(value, bool) or not isinstance(value, int | float) or not isfinite(value):
        raise StatsConfigError("'estatistica.frequencia_esperada_minima' deve ser um número.")
    if value <= 0:
        raise StatsConfigError("'estatistica.frequencia_esperada_minima' deve ser maior que zero.")
    return float(value)


@dataclass(frozen=True)
class StrategyObservation:
    """A estratégia de um trial e a linha da tabela a que ele pertence.

    Attributes:
        linha: Rótulo da linha: a sessão (`trials.day_number`) ou o grupo
            experimental (B6). Rótulos de uma mesma tabela devem ser comparáveis
            entre si, para ordenar, ou a ordem é dada em `linhas`.
        estrategia: Categoria classificada pela US-20; `None` = trial não
            classificado (fica fora da tabela, contado em `nao_classificados`).
    """

    linha: Hashable
    estrategia: str | None


@dataclass(frozen=True)
class ContingencyTable:
    """Tabela de contingência linha × estratégia (RN01), com o que nela falta (Cenário 3).

    Attributes:
        dimensao: O que as linhas são (`sessao` ou `grupo`).
        linhas: Rótulos das linhas, na ordem da tabela.
        categorias: Estratégias, na ordem das colunas, inclusive as ausentes.
        contagens: Trials por linha e categoria.
        categorias_ausentes: Categorias sem nenhum trial (coluna de zeros).
        linhas_vazias: Linhas sem nenhum trial classificado (linha de zeros).
        nao_classificados: Trials com `estrategia = None`, fora da tabela.
        avisos: Ressalvas legíveis (ausências, trials não classificados).
    """

    dimensao: str
    linhas: tuple[Hashable, ...]
    categorias: tuple[str, ...]
    contagens: tuple[tuple[int, ...], ...]
    categorias_ausentes: tuple[str, ...]
    linhas_vazias: tuple[Hashable, ...]
    nao_classificados: int
    avisos: tuple[str, ...]

    @property
    def total(self) -> int:
        return int(sum(sum(row) for row in self.contagens))

    def as_array(self) -> np.ndarray:
        return np.array(self.contagens, dtype=np.int64).reshape(
            len(self.linhas), len(self.categorias)
        )

    def as_record(self) -> dict[str, Any]:
        return {
            "dimensao": self.dimensao,
            "linhas": list(self.linhas),
            "categorias": list(self.categorias),
            "contagens": [list(row) for row in self.contagens],
            "total": self.total,
            "categorias_ausentes": list(self.categorias_ausentes),
            "linhas_vazias": list(self.linhas_vazias),
            "nao_classificados": self.nao_classificados,
            "avisos": list(self.avisos),
        }


def _ordered_labels(labels: Iterable[Hashable]) -> tuple[Hashable, ...]:
    unique = set(labels)
    try:
        return tuple(sorted(unique))
    except TypeError as exc:
        raise ValueError(
            "Rótulos de linha de tipos diferentes não podem ser ordenados: informe a ordem "
            "em 'linhas'."
        ) from exc


def build_contingency_table(
    observations: Iterable[StrategyObservation],
    *,
    categorias: Sequence[str] = DEFAULT_STRATEGIES,
    linhas: Sequence[Hashable] | None = None,
    dimensao: str = "sessao",
) -> ContingencyTable:
    """Monta a tabela linha × estratégia (RN01, RN04, Cenário 3).

    Args:
        observations: Uma observação por trial.
        categorias: Todas as estratégias possíveis, na ordem das colunas. Uma
            categoria sem trials aparece com zeros e é sinalizada.
        linhas: Ordem das linhas e linhas esperadas (ex.: as 4 sessões, mesmo as sem
            trial classificado). Padrão: os rótulos observados, ordenados.
        dimensao: O que as linhas são, para os textos (`sessao` ou `grupo`).

    Raises:
        ValueError: Categorias vazias ou repetidas, estratégia fora de `categorias`
            (nunca descartada em silêncio) ou linha fora de `linhas`.
    """
    categorias = tuple(categorias)
    if not categorias or len(set(categorias)) != len(categorias):
        raise ValueError("Informe as categorias de estratégia, sem repetição.")
    observations = tuple(observations)
    classified = [obs for obs in observations if obs.estrategia is not None]
    unknown = sorted({obs.estrategia for obs in classified} - set(categorias))
    if unknown:
        raise ValueError(
            f"Estratégia(s) fora das categorias {list(categorias)}: {unknown}. Confira a "
            "saída da US-20 ou as categorias informadas."
        )
    if linhas is None:
        row_labels = _ordered_labels(obs.linha for obs in classified)
    else:
        row_labels = tuple(linhas)
        if len(set(row_labels)) != len(row_labels):
            raise ValueError(f"Linhas repetidas em 'linhas': {list(row_labels)}.")
        outside = {obs.linha for obs in observations} - set(row_labels)
        if outside:
            raise ValueError(
                f"Observações com {_label(dimensao)} fora de 'linhas': {sorted(map(str, outside))}."
            )

    row_index = {label: i for i, label in enumerate(row_labels)}
    col_index = {name: j for j, name in enumerate(categorias)}
    counts = np.zeros((len(row_labels), len(categorias)), dtype=np.int64)
    for obs in classified:
        counts[row_index[obs.linha], col_index[obs.estrategia]] += 1

    ausentes = tuple(name for j, name in enumerate(categorias) if counts[:, j].sum() == 0)
    vazias = tuple(label for i, label in enumerate(row_labels) if counts[i].sum() == 0)
    nao_classificados = len(observations) - len(classified)
    avisos: list[str] = []
    for name in ausentes:
        avisos.append(
            f"Estratégia '{name}' ausente: nenhum trial classificado nela. A coluna aparece "
            "com zeros e fica fora do teste."
        )
    for label in vazias:
        avisos.append(
            f"{_label(dimensao).capitalize()} {label!s} sem nenhum trial classificado: linha de zeros, "
            "fora do teste."
        )
    if nao_classificados:
        avisos.append(
            f"{nao_classificados} trial(s) sem estratégia classificada ficaram fora da tabela."
        )
    return ContingencyTable(
        dimensao=dimensao,
        linhas=row_labels,
        categorias=categorias,
        contagens=tuple(tuple(int(v) for v in row) for row in counts),
        categorias_ausentes=ausentes,
        linhas_vazias=vazias,
        nao_classificados=nao_classificados,
        avisos=tuple(avisos),
    )


class AppliedTest(StrEnum):
    """Teste aplicado (RN02). Valores = texto gravado no resultado."""

    QUI_QUADRADO = "qui_quadrado"
    FISHER_EXATO_2X2 = "fisher_exato_2x2"
    FISHER_MONTE_CARLO = "fisher_monte_carlo"


@dataclass(frozen=True)
class IndependenceResult:
    """Resultado do teste de independência linha × estratégia (RN02, RN03).

    Attributes:
        tabela: A tabela completa, como reportada (com zeros).
        teste: Teste aplicado; `None` quando a tabela não permite teste.
        estatistica: Valor da estatística; `None` sem teste.
        nome_estatistica: `qui2`, `razao_de_chances` (Fisher 2×2) ou
            `probabilidade_da_tabela` (Fisher R×C).
        graus_liberdade: Do qui-quadrado; `None` nos demais.
        valor_p: Valor-p; `None` sem teste.
        justificativa: Por que este teste (ou nenhum) foi aplicado (RN02, RN03).
        limiar_frequencia_esperada: Limite usado na escolha.
        menor_frequencia_esperada: Menor célula esperada da tabela testada.
        celulas_abaixo_do_limiar: Quantas células esperadas ficaram abaixo do limite.
        linhas_testadas: Linhas que entraram no teste (sem as zeradas).
        categorias_testadas: Categorias que entraram no teste (sem as ausentes).
        frequencias_esperadas: Da tabela testada, na ordem acima.
        correcao_continuidade: Se a correção de Yates foi aplicada (só qui-quadrado).
        monte_carlo: `{"reamostragens", "semente"}` no Fisher R×C; `None` nos demais.
        avisos: Ressalvas da tabela e do teste.
    """

    tabela: ContingencyTable
    teste: AppliedTest | None
    estatistica: float | None
    nome_estatistica: str | None
    graus_liberdade: int | None
    valor_p: float | None
    justificativa: str
    limiar_frequencia_esperada: float
    menor_frequencia_esperada: float | None
    celulas_abaixo_do_limiar: int | None
    linhas_testadas: tuple[Hashable, ...]
    categorias_testadas: tuple[str, ...]
    frequencias_esperadas: tuple[tuple[float, ...], ...] | None
    correcao_continuidade: bool | None
    monte_carlo: dict[str, int] | None
    avisos: tuple[str, ...]

    def as_record(self) -> dict[str, Any]:
        """Registro JSON do resultado, com a justificativa da escolha (RN02, RN03)."""
        return {
            "tabela": self.tabela.as_record(),
            "teste": None if self.teste is None else self.teste.value,
            "estatistica": self.estatistica,
            "nome_estatistica": self.nome_estatistica,
            "graus_liberdade": self.graus_liberdade,
            "valor_p": self.valor_p,
            "justificativa": self.justificativa,
            "limiar_frequencia_esperada": self.limiar_frequencia_esperada,
            "menor_frequencia_esperada": self.menor_frequencia_esperada,
            "celulas_abaixo_do_limiar": self.celulas_abaixo_do_limiar,
            "linhas_testadas": list(self.linhas_testadas),
            "categorias_testadas": list(self.categorias_testadas),
            "frequencias_esperadas": (
                None
                if self.frequencias_esperadas is None
                else [list(row) for row in self.frequencias_esperadas]
            ),
            "correcao_continuidade": self.correcao_continuidade,
            "monte_carlo": self.monte_carlo,
            "avisos": list(self.avisos),
        }


def _positive(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not isfinite(value):
        raise ValueError(f"{name} deve ser um número finito.")
    if value <= 0:
        raise ValueError(f"{name} deve ser maior que zero.")
    return float(value)


def run_independence_test(
    tabela: ContingencyTable,
    *,
    frequencia_esperada_minima: float,
    reamostragens: int = MONTE_CARLO_REAMOSTRAGENS,
    semente: int = MONTE_CARLO_SEMENTE,
    correcao_continuidade: bool = True,
) -> IndependenceResult:
    """Qui-quadrado ou exato de Fisher, escolhido pelas frequências esperadas (RN02).

    Args:
        tabela: Tabela de `build_contingency_table` (sessão ou grupo × estratégia).
        frequencia_esperada_minima: Limite da regra (`load_min_expected_frequency`),
            explícito para que nenhum chamador escolha o teste com valor implícito.
        reamostragens: Reamostragens do Monte Carlo (Fisher R×C).
        semente: Semente do Monte Carlo, para reprodutibilidade.
        correcao_continuidade: Correção de Yates do qui-quadrado (só atua em 2×2).

    Returns:
        O resultado, sempre com a justificativa. Tabela com menos de 2 linhas ou 2
        categorias com trials → sem teste (`teste = None`), nunca um valor-p inventado.
    """
    limiar = _positive(frequencia_esperada_minima, "A frequência esperada mínima")
    if isinstance(reamostragens, bool) or not isinstance(reamostragens, int) or reamostragens < 1:
        raise ValueError("O número de reamostragens deve ser um inteiro positivo.")
    counts = tabela.as_array()
    keep_rows = counts.sum(axis=1) > 0
    keep_cols = counts.sum(axis=0) > 0
    reduced = counts[np.ix_(keep_rows, keep_cols)]
    linhas = tuple(label for label, keep in zip(tabela.linhas, keep_rows, strict=True) if keep)
    categorias = tuple(c for c, keep in zip(tabela.categorias, keep_cols, strict=True) if keep)
    avisos = list(tabela.avisos)
    base = {
        "tabela": tabela,
        "limiar_frequencia_esperada": limiar,
        "linhas_testadas": linhas,
        "categorias_testadas": categorias,
    }

    if reduced.shape[0] < 2 or reduced.shape[1] < 2:
        return IndependenceResult(
            teste=None,
            estatistica=None,
            nome_estatistica=None,
            graus_liberdade=None,
            valor_p=None,
            justificativa=(
                f"Nenhum teste aplicado: a tabela tem {reduced.shape[0]} linha(s) "
                f"e {reduced.shape[1]} estratégia(s) com trials; a independência só é testável "
                "com ao menos 2 de cada."
            ),
            menor_frequencia_esperada=None,
            celulas_abaixo_do_limiar=None,
            frequencias_esperadas=None,
            correcao_continuidade=None,
            monte_carlo=None,
            avisos=tuple(avisos),
            **base,
        )

    expected = expected_freq(reduced)
    menor = float(expected.min())
    abaixo = int((expected < limiar).sum())
    shape = f"{reduced.shape[0]}×{reduced.shape[1]}"
    common = {
        "menor_frequencia_esperada": menor,
        "celulas_abaixo_do_limiar": abaixo,
        "frequencias_esperadas": tuple(tuple(float(v) for v in row) for row in expected),
        **base,
    }

    if abaixo == 0:
        chi2 = stats.chi2_contingency(reduced, correction=correcao_continuidade)
        dof = int(chi2.dof)
        yates = correcao_continuidade and dof == 1
        return IndependenceResult(
            teste=AppliedTest.QUI_QUADRADO,
            estatistica=float(chi2.statistic),
            nome_estatistica="qui2",
            graus_liberdade=dof,
            valor_p=float(chi2.pvalue),
            justificativa=(
                f"Qui-quadrado de independência: todas as {expected.size} frequências "
                f"esperadas da tabela {shape} são >= {limiar:g} (menor = {menor:.3g})."
                + (" Com correção de continuidade de Yates (1 grau de liberdade)." if yates else "")
            ),
            correcao_continuidade=yates,
            monte_carlo=None,
            avisos=tuple(avisos),
            **common,
        )

    motivo = (
        f"{abaixo} de {expected.size} frequências esperadas da tabela {shape} ficaram abaixo "
        f"de {limiar:g} (menor = {menor:.3g}): o qui-quadrado não é confiável e foi trocado "
        "pelo exato de Fisher"
    )
    if reduced.shape == (2, 2):
        fisher = stats.fisher_exact(reduced)
        return IndependenceResult(
            teste=AppliedTest.FISHER_EXATO_2X2,
            estatistica=float(fisher.statistic),
            nome_estatistica="razao_de_chances",
            graus_liberdade=None,
            valor_p=float(fisher.pvalue),
            justificativa=f"{motivo} (2×2, exato, bilateral).",
            correcao_continuidade=None,
            monte_carlo=None,
            avisos=tuple(avisos),
            **common,
        )

    method = stats.MonteCarloMethod(n_resamples=reamostragens, rng=np.random.default_rng(semente))
    fisher = stats.fisher_exact(reduced, method=method)
    avisos.append(
        f"Fisher {shape}: valor-p estimado por Monte Carlo ({reamostragens} reamostragens, "
        f"semente {semente}); não é a enumeração exata."
    )
    return IndependenceResult(
        teste=AppliedTest.FISHER_MONTE_CARLO,
        estatistica=float(fisher.statistic),
        nome_estatistica="probabilidade_da_tabela",
        graus_liberdade=None,
        valor_p=float(fisher.pvalue),
        justificativa=(
            f"{motivo} ({shape}: Fisher–Freeman–Halton, valor-p por Monte Carlo com margens fixas)."
        ),
        correcao_continuidade=None,
        monte_carlo={"reamostragens": reamostragens, "semente": semente},
        avisos=tuple(avisos),
        **common,
    )


def render_markdown(result: IndependenceResult) -> str:
    """Relatório legível: tabela, teste, estatística, valor-p e justificativa (RN03)."""
    tabela = result.tabela
    dimensao = _label(tabela.dimensao)
    lines = [f"# US-23 — {dimensao} × estratégia", ""]
    header = f"| {dimensao} | " + " | ".join(tabela.categorias) + " | total |"
    lines += [header, "|---|" + "---:|" * (len(tabela.categorias) + 1)]
    for label, row in zip(tabela.linhas, tabela.contagens, strict=True):
        lines.append(f"| {label!s} | " + " | ".join(map(str, row)) + f" | {sum(row)} |")
    totals = tabela.as_array().sum(axis=0)
    lines.append("| **total** | " + " | ".join(map(str, totals)) + f" | {tabela.total} |")
    lines.append("")
    if result.teste is None:
        lines.append("- Teste: **nenhum**")
    else:
        lines.append(f"- Teste: **{result.teste.value}**")
        stat = f"- {result.nome_estatistica} = {result.estatistica:.6g}"
        if result.graus_liberdade is not None:
            stat += f" · graus de liberdade = {result.graus_liberdade}"
        lines += [stat, f"- valor-p = {result.valor_p:.6g}"]
    lines.append(f"- Justificativa: {result.justificativa}")
    if result.avisos:
        lines += ["", "Avisos:", ""]
        lines += [f"- {aviso}" for aviso in result.avisos]
    return "\n".join(lines) + "\n"
