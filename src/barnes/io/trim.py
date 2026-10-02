"""Recorte do intervalo útil do trial (US-03).

Descarta o tempo antes da soltura do animal e depois do fim do trial, para
que nenhuma métrica, evento ou ponto de trajetória calculado por estágios
posteriores do pipeline (pose, eventos, métricas) seja originado fora do
intervalo em que o animal estava de fato buscando o alvo.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from barnes.io.video import VideoMetadata

# Quantos quadros iniciais formam a linha de base "parado" contra a qual o
# movimento é comparado. Cobre a manipulação inicial (mão, cilindro) sem
# assumir que ela dura um tempo fixo em segundos — poucos quadros bastam
# porque é só para estimar o nível de ruído da cena parada.
_BASELINE_FRAMES = 5

# Quantos quadros consecutivos acima do limiar são exigidos para considerar
# que o movimento é o início real da busca, não um pico isolado de ruído
# (reflexo, compressão de vídeo, mão ainda saindo de quadro).
_SUSTAIN_FRAMES = 3

# Desvios-padrão acima da linha de base para marcar um quadro como "em
# movimento". Valor conservador — calibração fina fica para quando houver
# vídeos reais do LNBio (tarefa "validar nos 3 trials de G1").
_MOTION_THRESHOLD_STD = 4.0


class TrialIntervalError(Exception):
    """Intervalo útil inválido: início/fim fora do vídeo, ou fim antes do início."""


@dataclass(frozen=True)
class TrialInterval:
    """Intervalo útil de um trial — o trecho entre a soltura e o fim do processamento.

    Attributes:
        start_s: Início do intervalo, em segundos, relativo ao início do
            arquivo de vídeo (RN01, RN05 — é o tempo zero de toda latência).
        end_s: Fim do intervalo, em segundos, relativo ao início do arquivo
            de vídeo (RN01).
        start_frame: Quadro de início, derivado de `start_s` pelo fps real
            do vídeo (RN01 — representação alternativa em número de quadro).
        end_frame: Quadro de fim, derivado de `end_s` pelo fps real do vídeo.
        manually_adjusted: True se início ou fim vieram de valor informado
            pelo operador em vez da detecção automática (Cenário 2).
    """

    start_s: float
    end_s: float
    start_frame: int
    end_frame: int
    manually_adjusted: bool


def _frame_at(seconds: float, fps_real: float) -> int:
    return round(seconds * fps_real)


def detect_release_time(path: str, *, capture_factory=cv2.VideoCapture) -> float | None:
    """Estima o instante de soltura do animal por detecção de movimento (RN03).

    Compara cada quadro ao anterior (diferença absoluta em tons de cinza) e
    usa os primeiros `_BASELINE_FRAMES` quadros como linha de base do que é
    "parado" — cobre tanto um vídeo estático quanto a manipulação inicial do
    animal, sem presumir sua duração. O primeiro quadro em que o movimento
    fica acima da linha de base por `_SUSTAIN_FRAMES` quadros seguidos é
    reportado como o início da soltura (remoção do cilindro ou primeiro
    movimento do próprio animal).

    Args:
        path: Caminho do vídeo do trial.
        capture_factory: Construtor de `cv2.VideoCapture`, substituível em
            teste.

    Returns:
        O instante estimado, em segundos, ou `None` se não houver quadros
        suficientes ou nenhum movimento sustentado for detectado — nesse
        caso o chamador deve recorrer ao início do vídeo (0s) e deixar a
        confirmação com o operador.
    """
    capture = capture_factory(str(path))
    try:
        if not capture.isOpened():
            return None

        scores: list[float] = []
        timestamps_ms: list[float] = []
        previous_gray: np.ndarray | None = None
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            timestamps_ms.append(capture.get(cv2.CAP_PROP_POS_MSEC))
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
            if previous_gray is not None:
                scores.append(float(np.mean(np.abs(gray - previous_gray))))
            previous_gray = gray
    finally:
        capture.release()

    # scores[i] é o movimento entre o quadro i e o quadro i+1 (RN03).
    if len(scores) < _BASELINE_FRAMES + _SUSTAIN_FRAMES:
        return None

    baseline = np.array(scores[:_BASELINE_FRAMES])
    baseline_mean = float(np.mean(baseline))
    baseline_std = float(np.std(baseline))
    threshold = baseline_mean + _MOTION_THRESHOLD_STD * baseline_std + 1e-6

    above = np.array(scores) > threshold
    for i in range(len(above) - _SUSTAIN_FRAMES + 1):
        if above[i : i + _SUSTAIN_FRAMES].all():
            # scores[i] é o movimento que termina no quadro i+1 — é esse
            # quadro que marca o início do movimento sustentado.
            return timestamps_ms[i + 1] / 1000.0

    return None


def build_trial_interval(
    video: VideoMetadata,
    *,
    start_s: float | None = None,
    end_s: float | None = None,
    start_frame: int | None = None,
    end_frame: int | None = None,
) -> TrialInterval:
    """Resolve o intervalo útil de um trial, com detecção automática do início (US-03).

    Início e fim podem ser informados em segundos OU em número de quadro
    (RN01) — não os dois para o mesmo limite. Quando nenhum dos dois é
    informado para o início, a detecção automática de `detect_release_time`
    é usada (RN03); se ela não encontrar movimento, o início cai para 0s e
    `manually_adjusted` permanece `False` — a confirmação de um valor
    proposto (Cenário 1) é simplesmente chamar esta função sem sobrescrever
    nada. Quando nenhum dos dois é informado para o fim, usa-se o fim do
    vídeo, porque este card não inclui detecção automática de fuga (isso
    depende dos eventos por buraco de um card posterior).

    Informar qualquer um dos quatro parâmetros marca `manually_adjusted =
    True` (Cenário 2) — é o operador corrigindo a proposta automática.

    Args:
        video: Metadados já extraídos do vídeo por `load_trial_video`.
        start_s: Início do intervalo, em segundos.
        end_s: Fim do intervalo, em segundos.
        start_frame: Início do intervalo, em número de quadro.
        end_frame: Fim do intervalo, em número de quadro.

    Returns:
        O `TrialInterval` resolvido, com as duas representações (segundos e
        quadro) preenchidas.

    Raises:
        TrialIntervalError: Se início e fim forem informados para o mesmo
            limite (`start_s` e `start_frame` juntos, idem para o fim), se o
            fim não for maior que o início, ou se algum dos dois cair fora
            da duração do vídeo.
    """
    if start_s is not None and start_frame is not None:
        raise TrialIntervalError("Informe o início em segundos OU em número de quadro, não os dois.")
    if end_s is not None and end_frame is not None:
        raise TrialIntervalError("Informe o fim em segundos OU em número de quadro, não os dois.")

    manually_adjusted = any(
        value is not None for value in (start_s, start_frame, end_s, end_frame)
    )

    if start_frame is not None:
        resolved_start_s = start_frame / video.fps_real
    elif start_s is not None:
        resolved_start_s = start_s
    else:
        detected = detect_release_time(str(video.path))
        resolved_start_s = detected if detected is not None else 0.0

    if end_frame is not None:
        resolved_end_s = end_frame / video.fps_real
    elif end_s is not None:
        resolved_end_s = end_s
    else:
        resolved_end_s = video.duration_s

    if not (0.0 <= resolved_start_s <= video.duration_s):
        raise TrialIntervalError(
            f"Início do intervalo ({resolved_start_s:.3f}s) fora da duração do vídeo "
            f"(0 a {video.duration_s:.3f}s)."
        )
    if not (0.0 <= resolved_end_s <= video.duration_s):
        raise TrialIntervalError(
            f"Fim do intervalo ({resolved_end_s:.3f}s) fora da duração do vídeo "
            f"(0 a {video.duration_s:.3f}s)."
        )
    if resolved_end_s <= resolved_start_s:
        raise TrialIntervalError(
            f"Fim do intervalo ({resolved_end_s:.3f}s) deve ser maior que o início "
            f"({resolved_start_s:.3f}s)."
        )

    return TrialInterval(
        start_s=resolved_start_s,
        end_s=resolved_end_s,
        start_frame=_frame_at(resolved_start_s, video.fps_real),
        end_frame=_frame_at(resolved_end_s, video.fps_real),
        manually_adjusted=manually_adjusted,
    )


def seconds_from_trial_start(absolute_time_s: float, interval: TrialInterval) -> float:
    """Converte um tempo absoluto do vídeo para tempo relativo ao início do intervalo útil (RN05).

    Todo módulo que calcular uma latência (eventos, métricas) deve passar o
    tempo absoluto do vídeo por esta função antes de reportá-lo — o tempo
    zero de qualquer latência é a soltura, não o início do arquivo.
    """
    return absolute_time_s - interval.start_s


def is_within_interval(absolute_time_s: float, interval: TrialInterval) -> bool:
    """True se um instante absoluto do vídeo cai dentro do intervalo útil (RN02)."""
    return interval.start_s <= absolute_time_s <= interval.end_s


def trimmed_frame_range(interval: TrialInterval) -> range:
    """Índices de quadro — início e fim inclusive — que pertencem ao intervalo útil (RN02).

    Uso pretendido: qualquer estágio futuro do pipeline que itere quadros do
    vídeo (pose, eventos) deve iterar `trimmed_frame_range(interval)` em vez
    de `range(video.frame_count)`, para que nada fora do intervalo seja
    processado — aplicando o recorte a montante, e não como um filtro depois
    do fato.
    """
    return range(interval.start_frame, interval.end_frame + 1)
