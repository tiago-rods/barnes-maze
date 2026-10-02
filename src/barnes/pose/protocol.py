"""Parâmetros do protocolo de anotação de pose (US-06), lidos de `configs/default.yaml`.

São parâmetros do **protocolo** (decisão da equipe, registrada em
`docs/protocolo-anotacao.md`), não limiares de métrica do portão G3: definem
só como os quadros são amostrados para anotação e como a contagem por região
é reportada. Ficam em configuração, nunca no código, pela mesma regra do resto
do projeto — mudar o protocolo é mudar um número em `configs/`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from barnes.pose.regions import Region, RegionParams

DEFAULT_CONFIG_PATH = Path("configs/default.yaml")


class ProtocolConfigError(ValueError):
    """Seção `anotacao` ausente ou inválida em `configs/default.yaml`."""


@dataclass(frozen=True)
class SplitProportions:
    """Proporções de trials em treino/validação/teste (RN03)."""

    treino: float
    validacao: float
    teste: float


@dataclass(frozen=True)
class AnnotationProtocol:
    """Protocolo de anotação completo (RN02/RN03).

    Attributes:
        regions: Fronteiras entre centro, borda e proximidade de buraco.
        frames_per_region: Quantidade-alvo de quadros amostrados por região,
            por trial.
        min_gap_frames: Distância mínima, em quadros, entre dois quadros
            amostrados do mesmo trial — quadros vizinhos são quase idênticos
            e não acrescentam informação ao treino.
        split: Proporções da divisão por trial.
        seed: Semente que torna amostragem e divisão reprodutíveis.
    """

    regions: RegionParams
    frames_per_region: dict[Region, int]
    min_gap_frames: int
    split: SplitProportions
    seed: int


def _number(section: dict, key: str, path: str) -> float:
    value = section.get(key) if isinstance(section, dict) else None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ProtocolConfigError(f"'{path}.{key}' deve ser um número em configs/default.yaml.")
    return float(value)


def load_annotation_protocol(path: str | Path = DEFAULT_CONFIG_PATH) -> AnnotationProtocol:
    """Lê a seção `anotacao` do arquivo de configuração.

    Args:
        path: Caminho do YAML. Padrão: `configs/default.yaml`, relativo ao
            diretório de trabalho (a raiz do repositório).

    Returns:
        O protocolo validado.

    Raises:
        ProtocolConfigError: Se o arquivo não existir, a seção estiver
            ausente ou algum valor for inválido.
    """
    path = Path(path)
    if not path.is_file():
        raise ProtocolConfigError(f"Arquivo de configuração não encontrado: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    section = data.get("anotacao")
    if not isinstance(section, dict):
        raise ProtocolConfigError(f"Seção 'anotacao' ausente em {path}.")

    regioes = section.get("regioes", {})
    regions = RegionParams(
        center_radius_frac=_number(regioes, "centro_raio_frac", "anotacao.regioes"),
        hole_margin_radii=_number(regioes, "buraco_margem_raios", "anotacao.regioes"),
    )

    quantidades = section.get("quadros_por_regiao", {})
    frames_per_region = {
        region: int(_number(quantidades, region.value, "anotacao.quadros_por_regiao"))
        for region in Region
    }
    if any(count < 0 for count in frames_per_region.values()):
        raise ProtocolConfigError("'anotacao.quadros_por_regiao' não aceita valores negativos.")

    divisao = section.get("divisao", {})
    split = SplitProportions(
        treino=_number(divisao, "treino", "anotacao.divisao"),
        validacao=_number(divisao, "validacao", "anotacao.divisao"),
        teste=_number(divisao, "teste", "anotacao.divisao"),
    )

    return AnnotationProtocol(
        regions=regions,
        frames_per_region=frames_per_region,
        min_gap_frames=int(_number(section, "intervalo_minimo_quadros", "anotacao")),
        split=split,
        seed=int(_number(section, "semente", "anotacao")),
    )
