"""Índice de entropia da trajetória (US-20).

Função pura, sem banco e sem vídeo: recebe a trajetória do trial
(`barnes.pose.trajectory`, contrato em `docs/contrato-trajetoria.md`) e a
geometria da montagem, e devolve a entropia de Shannon, em bits (base 2), da
distribuição do **tempo** gasto pelo ponto do corpo em setores angulares ao
redor do centro da plataforma.

Não é a entropia da sequência de buracos checados — essa comparação cabe ao
sinal de adjacência da classificação (`barnes.strategy.signals`, US-20 RN02).
Este índice usa a trajetória contínua, independente de qualquer buraco ter
sido checado: uma busca aleatória (muitos cruzamentos, vai e volta pela
plataforma) espalha o tempo por muitos setores — entropia alta; uma busca
direta concentra o tempo em poucos — entropia baixa (Cenário 3 do US-20).

Convenção da equipe, sem resposta do laboratório (C4,
`docs/decisoes-sem-laboratorio.md` §10):

- **Janela temporal**: a mesma dos outros dois sinais da classificação (US-20
  RN02) — do início do intervalo útil até a primeira checagem do alvo
  (`until_s`), ou o trial inteiro se o alvo não foi checado (censurado, como
  em US-17); quem chama decide `until_s` a partir da sequência da US-15.
- **Setores**: o círculo (ângulo do ponto do corpo em torno do centro da
  plataforma, convenção de `holes.angle_deg`: 0° = +x, sentido horário na
  tela) é dividido em `n_setores` partes iguais, por padrão o número de
  buracos da montagem (`geometry.hole_count`) — a entropia máxima
  (distribuição uniforme) fica em `log2(N)`, a mesma escala de "quantos
  buracos poderiam ter sido visitados".
- **Tempo por amostra**: cada amostra válida conta como uma unidade de tempo
  (proxy do intervalo entre quadros, assumido ~constante); com fps variável
  (US-01) o índice sai com ressalva de aproximação, nunca é recusado.
- **Amostras insuficientes**: sem nenhuma amostra válida no trecho, a
  entropia é `None` (não calculada), nunca zero — zero é uma trajetória
  real concentrada num único setor, diferente de "sem dado".
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, log2

import numpy as np
import pyarrow as pa

from barnes.geometry.holes import MazeGeometry
from barnes.metrics.latency import DEFAULT_DISTANCE_POINT, TRAJECTORY_POINTS


class EntropyError(ValueError):
    """Entradas incoerentes para o cálculo de entropia da trajetória (US-20)."""


@dataclass(frozen=True)
class TrajectoryEntropy:
    """Entropia de Shannon da trajetória de um trial, em bits (US-20).

    Attributes:
        bits: Entropia em base 2 (log2); `None` se não calculada (sem amostra
            válida no trecho).
        n_setores: Número de setores angulares usados no histograma.
        n_amostras: Amostras válidas usadas (proxy do tempo em cada setor).
        contagem_por_setor: Contagem de amostras por setor, setor 0 primeiro
            (auditoria).
        ponto: Ponto do corpo usado.
        until_s: Tempo final do trecho considerado (`None` = sem corte, até o
            fim da trajetória).
        avisos: Ressalvas legíveis (fps variável, sem amostra).
    """

    bits: float | None
    n_setores: int
    n_amostras: int
    contagem_por_setor: tuple[int, ...]
    ponto: str
    until_s: float | None
    avisos: tuple[str, ...]

    @property
    def calculado(self) -> bool:
        return self.bits is not None

    @property
    def bits_maximo(self) -> float:
        """Entropia máxima possível com `n_setores` (distribuição uniforme)."""
        return log2(self.n_setores)


def compute_trajectory_entropy(
    trajectory: pa.Table,
    geometry: MazeGeometry,
    cm_per_px: float,
    *,
    ponto: str = DEFAULT_DISTANCE_POINT,
    until_s: float | None = None,
    n_setores: int | None = None,
) -> TrajectoryEntropy:
    """Entropia de Shannon, em bits, da distribuição angular da trajetória.

    Args:
        trajectory: Trajetória do trial (`read_trajectory`).
        geometry: Montagem do trial, para o centro da plataforma e o número
            de buracos (padrão de `n_setores`).
        cm_per_px: Escala px->cm da montagem (`barnes.db.calibration`).
        ponto: Ponto do corpo usado (o mesmo das US-16/18/19, por padrão).
        until_s: Tempo final do trecho, em segundos desde S; `None` = sem
            corte (trial inteiro, ou censurado — US-17 RN03).
        n_setores: Número de setores angulares; padrão: `geometry.hole_count`.

    Returns:
        A entropia e o que a audita.

    Raises:
        EntropyError: Ponto desconhecido, trajetória sem as colunas
            necessárias, `until_s` não finito/negativo ou `n_setores` < 2.
    """
    if ponto not in TRAJECTORY_POINTS:
        raise EntropyError(f"Ponto '{ponto}' desconhecido; use um de {', '.join(TRAJECTORY_POINTS)}.")
    if until_s is not None and (
        isinstance(until_s, bool) or not isinstance(until_s, int | float) or not isfinite(until_s)
    ):
        raise EntropyError("'until_s' deve ser um número finito de segundos, ou None.")
    if until_s is not None and until_s < 0:
        raise EntropyError(f"'until_s'={until_s} s é anterior a S (US-20).")
    setores = geometry.hole_count if n_setores is None else n_setores
    if isinstance(setores, bool) or not isinstance(setores, int) or setores < 2:
        raise EntropyError("'n_setores' deve ser um inteiro >= 2.")

    columns = ("t_s", f"{ponto}_x_cm_image", f"{ponto}_y_cm_image", f"{ponto}_valido", "fps_variavel")
    missing = [name for name in columns if name not in trajectory.column_names]
    if missing:
        raise EntropyError(f"Trajetória sem as colunas: {', '.join(missing)}.")
    t_s, x_cm, y_cm, valid, fps = (trajectory.column(name).to_numpy() for name in columns)
    valid = valid.astype(bool)

    keep = valid & (t_s >= 0)
    if until_s is not None:
        keep &= t_s <= until_s

    avisos: list[str] = []
    if bool(fps.any()):
        avisos.append("Vídeo com fps variável (US-01): entropia aproximada (amostra ~ tempo).")

    n_amostras = int(keep.sum())
    if n_amostras == 0:
        avisos.append("Entropia não calculada: nenhuma amostra válida no trecho.")
        return TrajectoryEntropy(
            bits=None,
            n_setores=setores,
            n_amostras=0,
            contagem_por_setor=(0,) * setores,
            ponto=ponto,
            until_s=until_s,
            avisos=tuple(avisos),
        )

    center_x_cm = geometry.center_x_px * cm_per_px
    center_y_cm = geometry.center_y_px * cm_per_px
    dx = x_cm[keep] - center_x_cm
    dy = y_cm[keep] - center_y_cm
    angle_deg = np.degrees(np.arctan2(dy, dx)) % 360.0
    setor_largura = 360.0 / setores
    indices = np.minimum((angle_deg / setor_largura).astype(np.int64), setores - 1)

    contagem = np.bincount(indices, minlength=setores)
    proporcao = contagem[contagem > 0] / n_amostras
    bits = float(-np.sum(proporcao * np.log2(proporcao)))
    if bits == 0.0:
        bits = 0.0  # normaliza -0.0 (toda amostra num só setor) para 0.0 nos relatórios

    return TrajectoryEntropy(
        bits=bits,
        n_setores=setores,
        n_amostras=n_amostras,
        contagem_por_setor=tuple(int(c) for c in contagem),
        ponto=ponto,
        until_s=until_s,
        avisos=tuple(avisos),
    )
