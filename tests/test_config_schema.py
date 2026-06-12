"""Testes para core.config_schema (configuração tipada)."""
from pathlib import Path

import pytest

from core.config_schema import AnalysisConfig


def test_default_values() -> None:
    config = AnalysisConfig()

    assert config.deepfake_noise_threshold == 50
    assert config.prnu_frame_limit == 50
    assert config.scene_threshold == 0.3
    assert config.deepfake_fast_mode is False


def test_from_dict_ignores_unknown_keys() -> None:
    config = AnalysisConfig.from_dict({
        "ela_quality": 75,
        "chave_inexistente": "valor",
    })

    assert config.ela_quality == 75
    assert not hasattr(config, "chave_inexistente")


def test_to_dict_round_trip() -> None:
    original = AnalysisConfig(copymove_features=3000, report_individual=True)
    restored = AnalysisConfig.from_dict(original.to_dict())

    assert restored == original


def test_json_file_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    original = AnalysisConfig(audio_segment_duration=15.0, scene_threshold=0.5)

    original.save_to_json(path)
    loaded = AnalysisConfig.from_json_file(path)

    assert loaded == original


def test_save_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "dir" / "config.json"
    AnalysisConfig().save_to_json(path)

    assert path.exists()


def test_from_json_file_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        AnalysisConfig.from_json_file(tmp_path / "nao_existe.json")
