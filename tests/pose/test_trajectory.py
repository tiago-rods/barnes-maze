"""Contrato do Parquet de trajetória (US-09, SCRUM-114): validado na escrita e na leitura."""

from __future__ import annotations

import math

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from barnes.pose.annotations import KEYPOINTS
from barnes.pose.trajectory import (
    ANGLE_CONVENTION,
    CONTRACT_VERSION,
    SCHEMA,
    TrajectoryContractError,
    read_metadata,
    read_trajectory,
    trajectory_path,
    with_metadata,
    write_trajectory,
)

NAN = math.nan


def _metadata(**overrides):
    return {
        "contrato_versao": CONTRACT_VERSION,
        "trial_id": 7,
        "execucao_id": 3,
        "content_hash": "a" * 64,
        "model_id": "sleap-maze-1-abc",
        "fps_real": 25.0,
        "fps_variavel": False,
        "cm_per_px": 0.1,
        "px_per_10cm": 100.0,
        "intervalo_inicio_s": 1.0,
        "intervalo_fim_s": 1.12,
        "convencao_angular": ANGLE_CONVENTION,
        "gerado_em": "2026-10-08T00:00:00+00:00",
    } | overrides


def _columns(n=3):
    """Três quadros: o do meio sem focinho (ausente, não preenchido)."""
    data = {
        "trial_id": [7] * n,
        "execucao_id": [3] * n,
        "quadro": [25 + i for i in range(n)],
        "t_s": [i / 25 for i in range(n)],
    }
    for point, base in zip(KEYPOINTS, (2.0, 1.0, 0.0), strict=True):
        data[f"{point}_x_cm_image"] = [base + i for i in range(n)]
        data[f"{point}_y_cm_image"] = [5.0] * n
        data[f"{point}_confianca"] = [0.9] * n
        data[f"{point}_valido"] = [True] * n
    data["focinho_x_cm_image"][1] = NAN
    data["focinho_y_cm_image"][1] = NAN
    data["focinho_confianca"][1] = NAN
    data["focinho_valido"][1] = False
    data["pose_valida"] = [True, False, True][:n] + [True] * max(0, n - 3)
    data["theta_deg_image"] = [0.0, NAN, 0.0][:n] + [0.0] * max(0, n - 3)
    data["interpolado"] = [False] * n
    data["fps_variavel"] = [False] * n
    return data


def _table(columns=None, metadata=None, schema=SCHEMA):
    table = pa.table(columns or _columns(), schema=schema)
    return with_metadata(table, metadata or _metadata())


def test_round_trip_keeps_rows_nans_and_metadata(tmp_path):
    path = write_trajectory(_table(), trajectory_path(tmp_path, 7))
    assert path.name == "trial_7.parquet"
    table = read_trajectory(path)
    assert table.num_rows == 3
    assert math.isnan(table.column("focinho_x_cm_image")[1].as_py())
    assert table.column("focinho_valido").to_pylist() == [True, False, True]
    assert read_metadata(table)["model_id"] == "sleap-maze-1-abc"
    assert not list(tmp_path.glob("*.tmp"))


def test_missing_column_is_rejected_and_nothing_is_written(tmp_path):
    columns = _columns()
    del columns["interpolado"]
    schema = pa.schema([f for f in SCHEMA if f.name != "interpolado"])
    path = tmp_path / "trial_7.parquet"
    with pytest.raises(TrajectoryContractError, match="Esquema"):
        write_trajectory(_table(columns, schema=schema), path)
    assert not path.exists()


def test_wrong_type_is_rejected():
    schema = pa.schema(
        [pa.field("quadro", pa.int64()) if f.name == "quadro" else f for f in SCHEMA]
    )
    with pytest.raises(TrajectoryContractError, match="Esquema"):
        write_trajectory(_table(schema=schema), "nao_usado.parquet")


def test_file_without_contract_metadata_is_rejected_on_read(tmp_path):
    path = tmp_path / "sem_metadados.parquet"
    pq.write_table(pa.table(_columns(), schema=SCHEMA), path)
    with pytest.raises(TrajectoryContractError, match="metadados"):
        read_trajectory(path)


def test_other_contract_version_is_rejected():
    with pytest.raises(TrajectoryContractError, match="v2"):
        write_trajectory(_table(metadata=_metadata(contrato_versao=2)), "x.parquet")


def test_missing_required_metadata_is_rejected():
    metadata = _metadata()
    del metadata["cm_per_px"]
    with pytest.raises(TrajectoryContractError, match="cm_per_px"):
        write_trajectory(_table(metadata=metadata), "x.parquet")


def test_nulls_are_rejected_absence_must_be_nan():
    columns = _columns()
    columns["focinho_x_cm_image"][1] = None
    with pytest.raises(TrajectoryContractError, match="nulos"):
        write_trajectory(_table(columns), "x.parquet")


def test_gap_in_frames_is_rejected():
    columns = _columns()
    columns["quadro"] = [25, 27, 28]
    with pytest.raises(TrajectoryContractError, match="contígua"):
        write_trajectory(_table(columns), "x.parquet")


def test_non_increasing_time_is_rejected():
    columns = _columns()
    columns["t_s"] = [0.0, 0.0, 0.08]
    with pytest.raises(TrajectoryContractError, match="t_s"):
        write_trajectory(_table(columns), "x.parquet")


def test_valid_flag_must_match_coordinates():
    columns = _columns()
    columns["focinho_valido"][1] = True  # diz válido, mas x/y são NaN
    with pytest.raises(TrajectoryContractError, match="focinho_valido"):
        write_trajectory(_table(columns), "x.parquet")


def test_pose_valid_requires_snout_and_body_center():
    columns = _columns()
    columns["pose_valida"][1] = True
    columns["theta_deg_image"][1] = 10.0
    with pytest.raises(TrajectoryContractError, match="pose_valida"):
        write_trajectory(_table(columns), "x.parquet")


def test_theta_must_be_nan_without_pose():
    columns = _columns()
    columns["theta_deg_image"][1] = 0.0  # θ "repetido" num quadro sem focinho
    with pytest.raises(TrajectoryContractError, match="theta_deg_image"):
        write_trajectory(_table(columns), "x.parquet")


def test_theta_outside_range_is_rejected():
    columns = _columns()
    columns["theta_deg_image"][0] = 360.0
    with pytest.raises(TrajectoryContractError, match=r"\[0, 360\)"):
        write_trajectory(_table(columns), "x.parquet")


def test_constant_columns_must_match_metadata():
    columns = _columns()
    columns["fps_variavel"] = [False, True, False]
    with pytest.raises(TrajectoryContractError, match="fps_variavel"):
        write_trajectory(_table(columns), "x.parquet")


def test_empty_trajectory_is_rejected():
    columns = {name: [] for name in SCHEMA.names}
    with pytest.raises(TrajectoryContractError, match="nenhuma linha"):
        write_trajectory(_table(columns), "x.parquet")
