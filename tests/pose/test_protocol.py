from pathlib import Path

import pytest

from barnes.pose.protocol import ProtocolConfigError, load_annotation_protocol
from barnes.pose.regions import Region

REPO_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "default.yaml"


def test_repository_config_has_valid_annotation_section() -> None:
    protocol = load_annotation_protocol(REPO_CONFIG)
    assert set(protocol.frames_per_region) == set(Region)
    split = protocol.split
    assert split.treino + split.validacao + split.teste == pytest.approx(1.0)
    assert protocol.min_gap_frames > 0


def test_missing_file_raises(tmp_path) -> None:
    with pytest.raises(ProtocolConfigError, match="não encontrado"):
        load_annotation_protocol(tmp_path / "nada.yaml")


def test_missing_section_raises(tmp_path) -> None:
    config = tmp_path / "default.yaml"
    config.write_text("encontrar:\n  distancia_cm: null\n", encoding="utf-8")
    with pytest.raises(ProtocolConfigError, match="anotacao"):
        load_annotation_protocol(config)


def test_null_value_raises_naming_the_key(tmp_path) -> None:
    config = tmp_path / "default.yaml"
    config.write_text(
        REPO_CONFIG.read_text(encoding="utf-8").replace(
            "centro_raio_frac: 0.5", "centro_raio_frac: null"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ProtocolConfigError, match="centro_raio_frac"):
        load_annotation_protocol(config)
