"""Contrato de dados da trajetória de pose por trial (US-09, SCRUM-114).

`data/interim/trial_<id>.parquet` é a entrada de todo o Épico D (eventos por
buraco, US-11 em diante), da qualidade de pose (US-10) e das métricas que vierem
depois. Por isso o esquema é fixo e verificado **na escrita e na leitura**: um
arquivo fora do contrato é recusado com `TrajectoryContractError`, em vez de
virar números plausíveis num estágio posterior. A descrição para humanos está
em `docs/contrato-trajetoria.md` — mantenha os dois em sincronia e, para
qualquer mudança incompatível, incremente `CONTRACT_VERSION`.

Ausência é dado: ponto não detectado fica NaN com `*_valido = false`, nunca
preenchido com o quadro anterior (US-09 RN05). Preencher é da US-10, que marca
`interpolado = true`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from barnes.pose.annotations import KEYPOINTS

CONTRACT_VERSION = 1
METADATA_KEY = b"barnes.trajetoria"

ANGLE_CONVENTION = (
    "theta_deg_image: direção centro_corpo -> focinho nos eixos da imagem; "
    "0 graus = +x (direita da imagem), crescente no sentido horário na tela "
    "(y cresce para baixo), em [0, 360) — a mesma convenção de holes.angle_deg (US-04)."
)

# Colunas na ordem do contrato. Posições em cm nos eixos da imagem: origem no
# canto superior esquerdo do quadro, y para baixo (sufixo _image, US-05 RN05).
SCHEMA = pa.schema(
    [
        ("trial_id", pa.int32()),
        ("execucao_id", pa.int32()),
        ("quadro", pa.int32()),
        ("t_s", pa.float64()),
        *[(f"{point}_{axis}_cm_image", pa.float64()) for point in KEYPOINTS for axis in ("x", "y")],
        *[(f"{point}_confianca", pa.float64()) for point in KEYPOINTS],
        *[(f"{point}_valido", pa.bool_()) for point in KEYPOINTS],
        ("pose_valida", pa.bool_()),
        ("theta_deg_image", pa.float64()),
        ("interpolado", pa.bool_()),
        ("fps_variavel", pa.bool_()),
    ]
)

REQUIRED_METADATA = (
    "contrato_versao",
    "trial_id",
    "execucao_id",
    "content_hash",
    "model_id",
    "fps_real",
    "fps_variavel",
    "cm_per_px",
    "px_per_10cm",
    "intervalo_inicio_s",
    "intervalo_fim_s",
    "convencao_angular",
    "gerado_em",
)


class TrajectoryContractError(ValueError):
    """Tabela ou arquivo de trajetória fora do contrato (`barnes.pose.trajectory`)."""


def trajectory_path(root: str | Path, trial_id: int) -> Path:
    """Caminho do arquivo da trajetória de um trial: um por trial (US-09 RN04)."""
    return Path(root) / f"trial_{trial_id}.parquet"


def with_metadata(table: pa.Table, metadata: dict[str, Any]) -> pa.Table:
    """Anexa os metadados do contrato (JSON) ao esquema da tabela."""
    return table.replace_schema_metadata(
        {METADATA_KEY: json.dumps(metadata, ensure_ascii=False, allow_nan=False)}
    )


def read_metadata(table: pa.Table) -> dict[str, Any]:
    """Metadados do contrato gravados no arquivo.

    Raises:
        TrajectoryContractError: Se ausentes ou ilegíveis.
    """
    raw = (table.schema.metadata or {}).get(METADATA_KEY)
    if raw is None:
        raise TrajectoryContractError("Trajetória sem metadados do contrato.")
    try:
        metadata = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TrajectoryContractError("Metadados da trajetória ilegíveis.") from exc
    if not isinstance(metadata, dict):
        raise TrajectoryContractError("Metadados da trajetória devem ser um objeto JSON.")
    return metadata


def validate_trajectory(table: pa.Table) -> dict[str, Any]:
    """Confere esquema, metadados e invariantes; devolve os metadados.

    Raises:
        TrajectoryContractError: Na primeira violação encontrada, com a coluna.
    """
    if not table.schema.equals(SCHEMA, check_metadata=False):
        expected = ", ".join(f"{f.name}:{f.type}" for f in SCHEMA)
        found = ", ".join(f"{f.name}:{f.type}" for f in table.schema)
        raise TrajectoryContractError(
            f"Esquema fora do contrato v{CONTRACT_VERSION}.\nEsperado: {expected}\n"
            f"Encontrado: {found}"
        )
    metadata = read_metadata(table)
    missing = [key for key in REQUIRED_METADATA if key not in metadata]
    if missing:
        raise TrajectoryContractError(f"Metadados obrigatórios ausentes: {', '.join(missing)}.")
    if metadata["contrato_versao"] != CONTRACT_VERSION:
        raise TrajectoryContractError(
            f"Contrato v{metadata['contrato_versao']}; este código lê a v{CONTRACT_VERSION}."
        )
    if table.num_rows == 0:
        raise TrajectoryContractError("Trajetória sem nenhuma linha (quadro).")
    for field in SCHEMA:
        if table.column(field.name).null_count:
            raise TrajectoryContractError(
                f"Coluna {field.name} tem nulos; ausência é NaN com *_valido = false."
            )

    col = {name: table.column(name).to_numpy() for name in SCHEMA.names}
    for name, key in (
        ("trial_id", "trial_id"),
        ("execucao_id", "execucao_id"),
        ("fps_variavel", "fps_variavel"),
    ):
        if not (col[name] == metadata[key]).all():
            raise TrajectoryContractError(
                f"Coluna {name} deve ser constante e igual aos metadados ({metadata[key]})."
            )

    frames = col["quadro"]
    if (frames < 0).any() or (np.diff(frames) != 1).any():
        raise TrajectoryContractError(
            "Coluna quadro deve ser contígua e crescente: uma linha por quadro do intervalo útil."
        )
    t = col["t_s"]
    if not np.isfinite(t).all() or (np.diff(t) <= 0).any():
        raise TrajectoryContractError("Coluna t_s deve ser finita e estritamente crescente.")

    for point in KEYPOINTS:
        x, y = col[f"{point}_x_cm_image"], col[f"{point}_y_cm_image"]
        valid = col[f"{point}_valido"]
        if (np.isinf(x) | np.isinf(y)).any():
            raise TrajectoryContractError(f"Coordenadas infinitas em {point}.")
        if not (valid == (np.isfinite(x) & np.isfinite(y))).all():
            raise TrajectoryContractError(
                f"{point}_valido deve ser verdadeiro exatamente quando x e y são finitos."
            )
        if np.isinf(col[f"{point}_confianca"]).any():
            raise TrajectoryContractError(f"Confiança infinita em {point}.")

    pose = col["pose_valida"]
    if (pose & ~(col["focinho_valido"] & col["centro_corpo_valido"])).any():
        raise TrajectoryContractError(
            "pose_valida exige focinho_valido e centro_corpo_valido no mesmo quadro."
        )
    theta = col["theta_deg_image"]
    finite_theta = np.isfinite(theta)
    if not (finite_theta == pose).all():
        raise TrajectoryContractError(
            "theta_deg_image deve ser finito exatamente nos quadros com pose_valida."
        )
    if ((theta[finite_theta] < 0) | (theta[finite_theta] >= 360)).any():
        raise TrajectoryContractError("theta_deg_image deve estar em [0, 360).")
    return metadata


def write_trajectory(table: pa.Table, path: str | Path) -> Path:
    """Valida e grava a trajetória atomicamente (`.tmp` + substituição).

    Raises:
        TrajectoryContractError: Se a tabela não cumprir o contrato — nada é gravado.
    """
    validate_trajectory(table)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    pq.write_table(table, temporary)
    temporary.replace(path)
    return path


def read_trajectory(path: str | Path) -> pa.Table:
    """Lê e valida uma trajetória; os metadados ficam em `read_metadata(tabela)`.

    Raises:
        TrajectoryContractError: Se o arquivo não cumprir o contrato.
        OSError: Se o arquivo não puder ser lido.
    """
    table = pq.read_table(Path(path))
    validate_trajectory(table)
    return table
