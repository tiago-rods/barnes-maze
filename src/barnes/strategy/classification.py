"""Classificação da estratégia de busca em espacial, serial ou aleatória (US-20).

Regra explícita e documentada (RN01), nunca um modelo treinado: combina os
três sinais da RN02 — cruzamentos do centro (`barnes.strategy.signals.
count_center_crossings`), adjacência angular dos buracos checados
(`barnes.strategy.signals.compute_angular_adjacency`) e erros até o alvo
(`barnes.metrics.errors.compute_errors`, US-17) — já calculados por quem
chama; este módulo só decide e registra os valores (RN06), nunca recalcula
sinal nenhum. Todos os limiares vêm de `configs/default.yaml`, seção
`estrategia` (RN03).

Critério (C4, sem resposta do laboratório — `docs/decisoes-sem-laboratorio.md`
§10), fundamentado em Harrison et al. 2006 (Learn Mem 13:809-816) e replicado
pela literatura derivada (Bhatt et al.; ConductScience; bio-protocol): cruzar o
centro é a assinatura da busca **aleatória**, nunca da espacial — o Cenário 2
de `docs/CARDS.md` descreve o trial espacial "cruzando o centro", o que
diverge dessa citação; tratado como inconsistência de redação do card (ver
`docs/definicoes-metricas.md`), não como regra.

- **Espacial**: foi direto ao alvo ou a um buraco vizinho dele
  (`adjacencia_angular_graus`), com poucos erros antes (`erros_ate_alvo_max`)
  e sem cruzar o centro (`cruzamentos_centro_min`).
- **Serial**: não é espacial, e existe uma sequência de ao menos
  `serial_min_buracos` buracos consecutivamente adjacentes entre si, no mesmo
  sentido, antes do alvo, também sem cruzar o centro.
- **Aleatória**: nem espacial nem serial — qualquer outra busca, tipicamente
  com cruzamentos pelo centro, buracos sem adjacência e mais erros.

Sem algum dos três sinais calculado (sem pose válida, ou sequência da US-15
indisponível), a classificação fica `None` — "não classificado" nunca é
confundido com "aleatória" (RN01: nenhuma categoria é um padrão/default).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from pathlib import Path

import yaml

from barnes.metrics.errors import TrialErrors
from barnes.strategy.signals import AngularAdjacency, CenterCrossings

DEFAULT_CONFIG_PATH = Path("configs/default.yaml")


class StrategyConfigError(ValueError):
    """Seção `estrategia` ausente ou inválida em `configs/default.yaml` (RN03)."""


class ClassificationError(ValueError):
    """Sinais incoerentes entre si (ex.: censura divergente) ao classificar (US-20)."""


class SearchStrategy(StrEnum):
    """Categoria de estratégia (RN01/RN02); valores = `trial_results.search_strategy`."""

    SPATIAL = "spatial"
    SERIAL = "serial"
    RANDOM = "random"


@dataclass(frozen=True)
class StrategyThresholds:
    """Limiares da regra de classificação, lidos de `configs/default.yaml` (RN03).

    `entropia_max_espacial` não entra aqui: por decisão da equipe não faz
    parte da regra de Harrison (§10 de `decisoes-sem-laboratorio.md`); a
    entropia é um índice calculado e registrado separadamente
    (`barnes.strategy.entropy`), nunca um dos três sinais da RN02.

    Attributes:
        cruzamentos_centro_min: Nº mínimo de cruzamentos do centro para
            desqualificar "espacial"/"serial" (ex.: 1 = nenhum cruzamento
            tolerado).
        adjacencia_angular_graus: Distância angular circular máxima para
            "um buraco de distância" (RN02; aplicada tanto ao primeiro buraco
            checado vs. o alvo quanto entre buracos checados consecutivos).
        erros_ate_alvo_max: Erros (US-17) admitidos antes do alvo na busca
            espacial.
        centro_zona_raio_frac: Fração do raio da circunferência dos buracos
            que define a zona central usada para contar cruzamentos.
        serial_min_buracos: Mínimo de buracos consecutivamente adjacentes, no
            mesmo sentido, para caracterizar "serial".
    """

    cruzamentos_centro_min: int
    adjacencia_angular_graus: float
    erros_ate_alvo_max: int
    centro_zona_raio_frac: float
    serial_min_buracos: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.cruzamentos_centro_min, bool)
            or not isinstance(self.cruzamentos_centro_min, int)
            or self.cruzamentos_centro_min < 0
        ):
            raise StrategyConfigError("'cruzamentos_centro_min' deve ser inteiro >= 0.")
        if (
            isinstance(self.adjacencia_angular_graus, bool)
            or not isinstance(self.adjacencia_angular_graus, int | float)
            or not isfinite(self.adjacencia_angular_graus)
            or not 0 <= self.adjacencia_angular_graus <= 180
        ):
            raise StrategyConfigError("'adjacencia_angular_graus' deve estar entre 0 e 180.")
        if (
            isinstance(self.erros_ate_alvo_max, bool)
            or not isinstance(self.erros_ate_alvo_max, int)
            or self.erros_ate_alvo_max < 0
        ):
            raise StrategyConfigError("'erros_ate_alvo_max' deve ser inteiro >= 0.")
        if (
            isinstance(self.centro_zona_raio_frac, bool)
            or not isinstance(self.centro_zona_raio_frac, int | float)
            or not 0 < self.centro_zona_raio_frac < 1
        ):
            raise StrategyConfigError("'centro_zona_raio_frac' deve estar entre 0 e 1 (exclusivo).")
        if (
            isinstance(self.serial_min_buracos, bool)
            or not isinstance(self.serial_min_buracos, int)
            or self.serial_min_buracos < 2
        ):
            raise StrategyConfigError("'serial_min_buracos' deve ser inteiro >= 2.")
        object.__setattr__(self, "adjacencia_angular_graus", float(self.adjacencia_angular_graus))
        object.__setattr__(self, "centro_zona_raio_frac", float(self.centro_zona_raio_frac))


def load_strategy_thresholds(path: str | Path = DEFAULT_CONFIG_PATH) -> StrategyThresholds:
    """Lê os limiares da regra de classificação da seção `estrategia` (RN03).

    Args:
        path: Caminho do YAML. Padrão: `configs/default.yaml`, relativo ao
            diretório de trabalho (a raiz do repositório).

    Raises:
        StrategyConfigError: Arquivo ou seção ausente, ou alguma chave
            ausente/inválida.
    """
    path = Path(path)
    if not path.is_file():
        raise StrategyConfigError(f"Arquivo de configuração não encontrado: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    section = data.get("estrategia") if isinstance(data, dict) else None
    if not isinstance(section, dict):
        raise StrategyConfigError(f"Seção 'estrategia' ausente em {path}.")
    chaves = (
        "cruzamentos_centro_min",
        "adjacencia_angular_graus",
        "erros_ate_alvo_max",
        "centro_zona_raio_frac",
        "serial_min_buracos",
    )
    ausentes = [chave for chave in chaves if section.get(chave) is None]
    if ausentes:
        raise StrategyConfigError(
            f"Chave(s) ausente(s) em 'estrategia' de {path}: {', '.join(ausentes)} (US-20 RN03)."
        )
    try:
        return StrategyThresholds(**{chave: section[chave] for chave in chaves})
    except StrategyConfigError:
        raise
    except (TypeError, ValueError) as exc:
        raise StrategyConfigError(str(exc)) from exc


@dataclass(frozen=True)
class StrategyClassification:
    """Resultado da classificação de um trial, com os três sinais (RN06).

    Attributes:
        categoria: `None` se não classificado (algum sinal não calculado) —
            nunca confundido com "aleatória".
        cruzamentos: Sinal 1 (RN02); `None` se não calculado.
        primeiro_buraco_distancia_deg: Sinal 2a — distância do primeiro
            buraco checado ao alvo; `None` se foi direto ao alvo.
        maior_sequencia_buracos: Sinal 2b — maior sequência adjacente.
        erros_ate_alvo: Sinal 3 (US-17); `None` se não calculado.
        primary_censurado: O alvo não foi checado na sequência (US-17 RN03).
        limiares: Os limiares usados (auditoria, RN03).
        avisos: Ressalvas legíveis (sinal ausente, censura).
    """

    categoria: SearchStrategy | None
    cruzamentos: int | None
    primeiro_buraco_distancia_deg: float | None
    maior_sequencia_buracos: int
    erros_ate_alvo: int | None
    primary_censurado: bool
    limiares: StrategyThresholds
    avisos: tuple[str, ...]

    @property
    def calculado(self) -> bool:
        return self.categoria is not None

    def as_trial_results(self) -> dict[str, str | None]:
        """A coluna de estratégia de `trial_results` (US-20); `None` se não classificado."""
        return {"search_strategy": None if self.categoria is None else self.categoria.value}

    def sinais_auditoria(self) -> dict[str, object]:
        """Os três sinais, para registro caso a caso (RN06)."""
        return {
            "cruzamentos_centro": self.cruzamentos,
            "primeiro_buraco_distancia_deg": self.primeiro_buraco_distancia_deg,
            "maior_sequencia_buracos_adjacentes": self.maior_sequencia_buracos,
            "erros_ate_alvo": self.erros_ate_alvo,
            "primary_censurado": self.primary_censurado,
        }


def _nao_classificado(
    crossings: CenterCrossings,
    adjacency: AngularAdjacency,
    errors: TrialErrors,
    limiares: StrategyThresholds,
    aviso: str,
) -> StrategyClassification:
    return StrategyClassification(
        categoria=None,
        cruzamentos=crossings.cruzamentos,
        primeiro_buraco_distancia_deg=adjacency.primeiro_buraco_distancia_deg,
        maior_sequencia_buracos=adjacency.maior_sequencia_buracos,
        erros_ate_alvo=errors.ate_alvo,
        primary_censurado=adjacency.primary_censurado,
        limiares=limiares,
        avisos=(aviso,),
    )


def classify_strategy(
    crossings: CenterCrossings,
    adjacency: AngularAdjacency,
    errors: TrialErrors,
    *,
    thresholds: StrategyThresholds,
) -> StrategyClassification:
    """Classifica a estratégia de um trial a partir dos três sinais já calculados (RN01/RN02).

    Args:
        crossings: Sinal 1 (`count_center_crossings`), no mesmo trecho "até o
            alvo" dos outros dois.
        adjacency: Sinal 2 (`compute_angular_adjacency`), sobre a sequência da
            US-15 no referencial da sala (RN05).
        errors: Sinal 3 (`compute_errors`, US-17), sobre a mesma sequência.
        thresholds: Limiares da regra (`load_strategy_thresholds`).

    Returns:
        A categoria e os três sinais, para auditoria caso a caso (RN06).
        `categoria = None` (não "aleatória") se cruzamentos ou erros não
        foram calculados.

    Raises:
        ClassificationError: `adjacency` e `errors` divergem sobre o alvo ter
            sido checado — sinal de que vieram de sequências diferentes.
    """
    if not crossings.calculado:
        return _nao_classificado(
            crossings,
            adjacency,
            errors,
            thresholds,
            "Não classificado: cruzamentos do centro não calculados (sem pose válida no trecho).",
        )
    if errors.total is None:
        return _nao_classificado(
            crossings,
            adjacency,
            errors,
            thresholds,
            "Não classificado: erros até o alvo não calculados (US-17).",
        )
    if adjacency.primary_censurado != errors.primary_censurado:
        raise ClassificationError(
            "Sinais de adjacência e de erros divergem sobre a censura (alvo checado ou não); "
            "confira se os dois vieram da mesma sequência da US-15."
        )

    espacial = (
        errors.ate_alvo <= thresholds.erros_ate_alvo_max
        and (
            adjacency.primeiro_buraco_distancia_deg is None
            or adjacency.primeiro_buraco_distancia_deg <= thresholds.adjacencia_angular_graus
        )
        and crossings.cruzamentos < thresholds.cruzamentos_centro_min
    )
    serial = (
        not espacial
        and adjacency.maior_sequencia_buracos >= thresholds.serial_min_buracos
        and crossings.cruzamentos < thresholds.cruzamentos_centro_min
    )
    categoria = (
        SearchStrategy.SPATIAL if espacial else SearchStrategy.SERIAL if serial else SearchStrategy.RANDOM
    )

    return StrategyClassification(
        categoria=categoria,
        cruzamentos=crossings.cruzamentos,
        primeiro_buraco_distancia_deg=adjacency.primeiro_buraco_distancia_deg,
        maior_sequencia_buracos=adjacency.maior_sequencia_buracos,
        erros_ate_alvo=errors.ate_alvo,
        primary_censurado=adjacency.primary_censurado,
        limiares=thresholds,
        avisos=crossings.avisos + adjacency.avisos,
    )
