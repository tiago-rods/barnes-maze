"""Contagem e sequência de erros de um trial (US-17).

Função pura, sem banco, sem vídeo e **sem trajetória** (RN02): a única entrada é a
sequência de visitação do trial — a sequência cronológica dos buracos checados da
US-15, entrada canônica dos Épicos E e F (US-15 RN03) — mais a definição de erro
lida de `configs/default.yaml` (seção `erro`, pergunta C3). Trocar a definição é só
chamar `compute_errors` de novo sobre a mesma sequência (RN05): nada aqui abre
vídeo ou Parquet.

A US-15 ainda não existe. Por isso a entrada é um tipo mínimo e explícito,
`VisitItem`, com só o que o erro precisa (buraco na plataforma e posição na sala,
início da checagem, dwell e se é o alvo), e `VisitSequence` tem um estado
"não avaliada" explícito: sem sequência, nada é calculado (`None`), o que é
diferente de "o animal não errou" (sequência avaliada, zero erros). Quando a
US-15 existir, ela produz estes itens; este módulo não fabrica nenhum.

Convenções (registradas em `docs/definicoes-metricas.md`, seção "Erro"):

- Erro = checagem de um buraco que não é o alvo (`alvo = False`). Com o critério
  `acima_de_duracao`, só conta se `dwell_s >= erro.duracao_minima_s` (inclusivo).
- Cada checagem conta: revisitar um buraco incorreto é um novo erro.
- Checagens do alvo nunca são erro, qualquer que seja o dwell.
- `total_errors`: erros no trial inteiro, inclusive depois de achar o alvo.
- `primary_errors` (erros até a descoberta do alvo, RN03): erros com início
  **antes** da primeira checagem do alvo na sequência. Esse corte é a descoberta
  D do alvo (US-11 RN05, `primary_latency` da US-16) porque o item da US-15
  começa no tempo de descoberta do buraco; o corte é lido da sequência, nunca de
  `barnes.events.discovery`, para manter RN02. Se o alvo não aparece na sequência,
  `primary_errors = total_errors` com `primary_censurado = True` — como na
  censura da US-16, o trial sem descoberta não é descartado nem recebe zero.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise
from math import isfinite
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path("configs/default.yaml")


class ErrorConfigError(ValueError):
    """Seção `erro` ausente ou inválida em `configs/default.yaml` (RN01, C3)."""


class ErrorCriterion(StrEnum):
    """O que conta como erro (RN01, pergunta C3). Valores = texto aceito no YAML."""

    QUALQUER_BURACO_INCORRETO = "qualquer_buraco_incorreto"
    ACIMA_DE_DURACAO = "acima_de_duracao"


def _finite_number(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int | float) and isfinite(value)


@dataclass(frozen=True)
class ErrorDefinition:
    """Definição de erro em uso (seção `erro` de `configs/default.yaml`).

    Attributes:
        criterio: `qualquer_buraco_incorreto` ou `acima_de_duracao`.
        duracao_minima_s: Dwell mínimo, em segundos, para uma checagem incorreta
            contar como erro. Obrigatório (> 0) com `acima_de_duracao` e
            proibido com `qualquer_buraco_incorreto` — um valor ali seria
            ignorado em silêncio, e a configuração ficaria ambígua.
    """

    criterio: ErrorCriterion
    duracao_minima_s: float | None = None

    def __post_init__(self) -> None:
        criterio = ErrorCriterion(self.criterio)
        object.__setattr__(self, "criterio", criterio)
        if criterio is ErrorCriterion.QUALQUER_BURACO_INCORRETO:
            if self.duracao_minima_s is not None:
                raise ValueError(
                    "Com o critério 'qualquer_buraco_incorreto' a duração mínima não se "
                    "aplica: deixe 'erro.duracao_minima_s' vazio (null)."
                )
            return
        if not _finite_number(self.duracao_minima_s) or self.duracao_minima_s <= 0:
            raise ValueError(
                "Com o critério 'acima_de_duracao', 'erro.duracao_minima_s' deve ser um "
                "número de segundos maior que zero."
            )
        object.__setattr__(self, "duracao_minima_s", float(self.duracao_minima_s))

    def descricao(self) -> str:
        """Texto legível da definição, para avisos e relatórios."""
        if self.criterio is ErrorCriterion.QUALQUER_BURACO_INCORRETO:
            return "qualquer checagem de buraco incorreto"
        return f"checagem de buraco incorreto com dwell >= {self.duracao_minima_s:g} s"


def load_error_definition(path: str | Path = DEFAULT_CONFIG_PATH) -> ErrorDefinition:
    """Lê a definição de erro da seção `erro` do arquivo de configuração (RN01).

    Args:
        path: Caminho do YAML. Padrão: `configs/default.yaml`, relativo ao
            diretório de trabalho (a raiz do repositório).

    Raises:
        ErrorConfigError: Arquivo ou seção ausente, `erro.criterio` vazio (`null`)
            ou desconhecido, ou `erro.duracao_minima_s` incoerente com o critério.
            Os valores de produção ficam `null` até o laboratório responder C3;
            sem eles os erros não são contados — este erro é esperado até lá,
            não um defeito.
    """
    path = Path(path)
    if not path.is_file():
        raise ErrorConfigError(f"Arquivo de configuração não encontrado: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    section = data.get("erro") if isinstance(data, Mapping) else None
    if not isinstance(section, Mapping):
        raise ErrorConfigError(f"Seção 'erro' ausente em {path}.")

    criterio = section.get("criterio")
    if criterio is None:
        raise ErrorConfigError(
            "'erro.criterio' está vazio em configs/default.yaml: a definição de erro vem "
            "da resposta do laboratório à pergunta C3 e, sem ela, os erros "
            "(total_errors/primary_errors) não podem ser contados (US-17 RN01)."
        )
    opcoes = ", ".join(c.value for c in ErrorCriterion)
    if not isinstance(criterio, str) or criterio not in {c.value for c in ErrorCriterion}:
        raise ErrorConfigError(f"'erro.criterio' = {criterio!r} desconhecido; use um de: {opcoes}.")

    duracao = section.get("duracao_minima_s")
    if criterio == ErrorCriterion.ACIMA_DE_DURACAO and duracao is None:
        raise ErrorConfigError(
            "'erro.duracao_minima_s' está vazio em configs/default.yaml, mas o critério "
            "'acima_de_duracao' exige a duração mínima (pergunta C3, US-17 RN01)."
        )
    try:
        return ErrorDefinition(criterio=ErrorCriterion(criterio), duracao_minima_s=duracao)
    except ValueError as exc:
        raise ErrorConfigError(str(exc)) from exc


@dataclass(frozen=True)
class VisitItem:
    """Uma checagem de buraco da sequência de visitação (contrato mínimo da US-15).

    Só os campos de que o erro precisa; a US-15 completa (ordem, tempos de
    descoberta e entrada, dwell) é um superconjunto. Posições levam o sufixo do
    referencial (US-05 RN05).

    Attributes:
        buraco_platform: Índice do buraco na montagem, 0..N-1.
        angulo_deg_room: Posição do buraco na sala, em graus [0, 360)
            (`barnes.geometry.reference_frame.hole_to_room_angle`) — a posição
            comparável entre trials (US-05).
        inicio_s: Início da checagem, em segundos desde S (início do intervalo
            útil): o tempo de descoberta desse buraco nessa checagem.
        dwell_s: Permanência na checagem, em segundos (US-14); `None` se o dwell
            não foi medido. Só é exigido pelo critério `acima_de_duracao`.
        alvo: O buraco é o buraco-alvo do trial.
    """

    buraco_platform: int
    angulo_deg_room: float
    inicio_s: float
    dwell_s: float | None
    alvo: bool

    def __post_init__(self) -> None:
        if (
            isinstance(self.buraco_platform, bool)
            or not isinstance(self.buraco_platform, int)
            or self.buraco_platform < 0
        ):
            raise ValueError("'buraco_platform' deve ser um índice de buraco inteiro >= 0.")
        if not _finite_number(self.angulo_deg_room) or not 0 <= self.angulo_deg_room < 360:
            raise ValueError("'angulo_deg_room' deve ser um ângulo finito em [0, 360).")
        if not _finite_number(self.inicio_s):
            raise ValueError("'inicio_s' deve ser um número finito de segundos.")
        if self.inicio_s < 0:
            raise ValueError(
                f"Checagem em inicio_s={self.inicio_s} s, antes de S: o tempo zero é o "
                "início do intervalo útil (US-16 RN04). Confira a referência de tempo."
            )
        if self.dwell_s is not None and (not _finite_number(self.dwell_s) or self.dwell_s < 0):
            raise ValueError("'dwell_s' deve ser um número finito >= 0, ou None se não medido.")
        if not isinstance(self.alvo, bool):
            raise TypeError("'alvo' deve ser True ou False.")


@dataclass(frozen=True)
class VisitSequence:
    """A sequência de visitação de um trial, com o estado "não avaliada" explícito.

    - `VisitSequence.avaliada(itens)`: a sequência foi montada (US-15); pode ser
      vazia — o animal não checou nenhum buraco, e zero erros é um resultado real;
    - `VisitSequence.nao_avaliada()`: não há sequência (ex.: US-15 ainda não
      implementada, eventos não calculados) — os erros não são calculados.

    Os itens devem chegar em ordem cronológica **estrita** de `inicio_s` (US-15
    RN01): uma sequência fora de ordem é recusada, nunca reordenada em silêncio,
    porque indica defeito de quem a montou.

    Attributes:
        disponivel: A sequência existe para este trial.
        itens: As checagens, em ordem cronológica.
    """

    disponivel: bool
    itens: tuple[VisitItem, ...] = ()

    def __post_init__(self) -> None:
        itens = tuple(self.itens)
        object.__setattr__(self, "itens", itens)
        if not self.disponivel:
            if itens:
                raise ValueError("Sequência não avaliada não pode ter itens.")
            return
        for anterior, atual in pairwise(itens):
            if atual.inicio_s <= anterior.inicio_s:
                raise ValueError(
                    f"Sequência de visitação fora de ordem cronológica estrita: checagem em "
                    f"{atual.inicio_s} s depois de uma em {anterior.inicio_s} s (US-15 RN01)."
                )
        alvos = {item.buraco_platform for item in itens if item.alvo}
        if len(alvos) > 1:
            raise ValueError(
                f"Mais de um buraco marcado como alvo na mesma sequência: {sorted(alvos)}."
            )
        if alvos and any(not item.alvo and item.buraco_platform in alvos for item in itens):
            raise ValueError(
                f"O buraco {next(iter(alvos))} aparece como alvo e como não alvo na mesma "
                "sequência."
            )

    @classmethod
    def avaliada(cls, itens: Iterable[VisitItem]) -> VisitSequence:
        return cls(disponivel=True, itens=tuple(itens))

    @classmethod
    def nao_avaliada(cls) -> VisitSequence:
        return cls(disponivel=False)


@dataclass(frozen=True)
class TrialErrors:
    """Erros de um trial sob uma definição (US-17 RN03).

    Attributes:
        definicao: Definição de erro usada.
        sequencia: As checagens que contaram como erro, em ordem cronológica;
            `None` se não calculado.
        total: Contagem total de erros no trial (`total_errors`); `None` se não
            calculado.
        ate_alvo: Erros antes da primeira checagem do alvo (`primary_errors`);
            `None` se não calculado.
        primary_censurado: O alvo não foi checado na sequência, então `ate_alvo`
            cobre o trial inteiro (contagem censurada, não zero); `None` se não
            calculado.
        avisos: Ressalvas legíveis (sequência ausente, dwell não medido, alvo não
            checado).
    """

    definicao: ErrorDefinition
    sequencia: tuple[VisitItem, ...] | None
    total: int | None
    ate_alvo: int | None
    primary_censurado: bool | None
    avisos: tuple[str, ...]

    @property
    def calculado(self) -> bool:
        return self.total is not None

    @property
    def buracos_platform(self) -> tuple[int, ...] | None:
        """Sequência ordenada dos buracos incorretos, como índices da montagem."""
        if self.sequencia is None:
            return None
        return tuple(item.buraco_platform for item in self.sequencia)

    @property
    def angulos_deg_room(self) -> tuple[float, ...] | None:
        """Sequência ordenada dos buracos incorretos, como posições na sala (US-05)."""
        if self.sequencia is None:
            return None
        return tuple(item.angulo_deg_room for item in self.sequencia)

    def as_trial_results(self) -> dict[str, int | None]:
        """As duas colunas de erro de `trial_results` (`docs/DER.md`).

        `None` só quando não calculado (sem sequência, ou dwell não medido sob
        `acima_de_duracao`) — nunca no lugar de zero erros.
        """
        return {"primary_errors": self.ate_alvo, "total_errors": self.total}


def _nao_calculado(definicao: ErrorDefinition, aviso: str) -> TrialErrors:
    return TrialErrors(
        definicao=definicao,
        sequencia=None,
        total=None,
        ate_alvo=None,
        primary_censurado=None,
        avisos=(aviso,),
    )


def compute_errors(sequence: VisitSequence, definicao: ErrorDefinition) -> TrialErrors:
    """Contagem, sequência e erros até o alvo, só a partir da sequência de visitação.

    Args:
        sequence: Sequência de visitação do trial (US-15). Enquanto ela não
            existir, passe `VisitSequence.nao_avaliada()`: nada é calculado.
        definicao: Definição de erro (`load_error_definition`), explícita para que
            nenhum chamador conte erros com uma definição implícita.

    Returns:
        Os erros do trial. Com `acima_de_duracao`, se alguma checagem incorreta não
        tem dwell medido, nada é calculado: contá-la ou descartá-la seria inventar
        a duração.
    """
    if not sequence.disponivel:
        return _nao_calculado(
            definicao,
            "Erros não calculados: a sequência de visitação (US-15) não está disponível. "
            "Isto não é 'zero erros'.",
        )

    incorretas = [item for item in sequence.itens if not item.alvo]
    if definicao.criterio is ErrorCriterion.ACIMA_DE_DURACAO:
        sem_dwell = [item for item in incorretas if item.dwell_s is None]
        if sem_dwell:
            tempos = ", ".join(f"{item.inicio_s:g} s" for item in sem_dwell)
            return _nao_calculado(
                definicao,
                f"Erros não calculados: o critério é '{definicao.descricao()}', mas "
                f"{len(sem_dwell)} checagem(ns) incorreta(s) não têm dwell medido (US-14): "
                f"{tempos}.",
            )
        minimo = definicao.duracao_minima_s
        erros = tuple(item for item in incorretas if item.dwell_s >= minimo)
    else:
        erros = tuple(incorretas)

    avisos: list[str] = []
    primeiro_alvo = next((item.inicio_s for item in sequence.itens if item.alvo), None)
    if primeiro_alvo is None:
        ate_alvo = len(erros)
        avisos.append(
            "O alvo não foi checado na sequência: 'primary_errors' conta os erros do trial "
            "inteiro e fica marcado como censurado."
        )
    else:
        ate_alvo = sum(1 for item in erros if item.inicio_s < primeiro_alvo)

    return TrialErrors(
        definicao=definicao,
        sequencia=erros,
        total=len(erros),
        ate_alvo=ate_alvo,
        primary_censurado=primeiro_alvo is None,
        avisos=tuple(avisos),
    )
