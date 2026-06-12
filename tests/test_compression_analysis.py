"""Testes para modules.compression_analysis (Lei de Benford e Fourier).

Os métodos estatísticos são testados isoladamente, sem FFmpeg: o módulo é
instanciado via ``__new__`` para pular a checagem de binários no PATH.
"""
import json
import math
from pathlib import Path

import numpy as np

from modules.compression_analysis import CompressionAnalysisModule


def _module() -> CompressionAnalysisModule:
    return CompressionAnalysisModule.__new__(CompressionAnalysisModule)


def _benford_conformant_sizes() -> list[int]:
    """Gera tamanhos cuja distribuição de primeiro dígito segue Benford."""
    sizes = []
    for digit in range(1, 10):
        count = round(300 * math.log10(1 + 1 / digit))
        sizes.extend(digit * 1000 + i for i in range(count))
    return sizes


def test_benford_conformant_data_is_normal() -> None:
    result = _module()._analyze_benford(_benford_conformant_sizes())

    assert result["status"] == "Normal"
    assert result["divergence_score"] < 0.05


def test_benford_anomalous_data_is_flagged() -> None:
    # Todos os tamanhos começam com dígito 9: viola fortemente Benford.
    sizes = [9000 + i for i in range(200)]

    result = _module()._analyze_benford(sizes)

    assert "Anômalo" in result["status"]
    assert result["divergence_score"] > 0.15


def test_benford_empty_data_returns_error() -> None:
    assert _module()._analyze_benford([]) == {"error": "Empty data"}


def test_benford_ignores_non_positive_sizes() -> None:
    result = _module()._analyze_benford([0, 0, 0])

    assert result == {"error": "Empty data"}


def test_fourier_detects_gop_period() -> None:
    # Sinal senoidal com período de 12 frames (GOP típico).
    n = 240
    sizes = [int(10000 + 5000 * np.cos(2 * np.pi * i / 12)) for i in range(n)]

    result = _module()._analyze_fourier(sizes)

    assert 11 <= result["dominant_period_frames"] <= 13
    assert result["status"] == "Padrão GOP Forte"


def test_fourier_short_sample_is_rejected() -> None:
    result = _module()._analyze_fourier([100] * 10)

    assert result["status"] == "Amostra insuficiente"


def test_conclusion_mentions_benford_violation() -> None:
    module = _module()
    benford = {"status": "Anômalo (Possível dupla compressão)"}
    fourier = {"peak_strength": 1.0, "dominant_period_frames": 0.0}

    conclusion = module._generate_conclusion(benford, fourier)

    assert "Lei de Benford" in conclusion


def test_conclusion_mentions_rigid_gop() -> None:
    module = _module()
    benford = {"status": "Normal"}
    fourier = {"peak_strength": 8.0, "dominant_period_frames": 12.0}

    conclusion = module._generate_conclusion(benford, fourier)

    assert "GOP" in conclusion


class _FakeFFmpeg:
    """Substitui o FFmpegAdapter para testar run() sem binários externos."""

    def __init__(self, sizes: list[int]) -> None:
        self._sizes = sizes

    def extract_frame_sizes(self, input_file: Path) -> dict[str, list[int]]:
        return {"all": self._sizes, "I": [], "P": [], "B": []}


def test_run_returns_result_data_on_success(case_manager) -> None:
    """Regressão: run() deve retornar o resultado (antes retornava None)."""
    sizes = _benford_conformant_sizes()
    module = _module()
    module.cm = case_manager
    module.logger = case_manager.get_logger()
    module.ffmpeg = _FakeFFmpeg(sizes)

    result = module.run(Path("video.mp4"), output_filename="compression.json")

    assert result is not None
    assert result["total_frames"] == len(sizes)
    assert "conclusion" in result
    # O JSON salvo deve espelhar o retorno
    saved = json.loads(
        (case_manager.results_dir / "compression.json").read_text(encoding="utf-8")
    )
    assert saved["total_frames"] == result["total_frames"]


def test_run_returns_error_dict_on_failure(case_manager) -> None:
    """Falha do adapter não deve propagar exceção: retorna {'error': ...}."""

    class _BrokenFFmpeg:
        def extract_frame_sizes(self, input_file: Path) -> dict:
            raise RuntimeError("ffprobe indisponível")

    module = _module()
    module.cm = case_manager
    module.logger = case_manager.get_logger()
    module.ffmpeg = _BrokenFFmpeg()

    result = module.run(Path("video.mp4"))

    assert result == {"error": "ffprobe indisponível"}
