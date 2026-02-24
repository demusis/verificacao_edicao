"""
Configuração centralizada para análise forense.

Este módulo define a estrutura de configuração tipada usando dataclasses,
eliminando a necessidade de dicionários espalhados pelo código.
"""
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional
import json


@dataclass
class AnalysisConfig:
    """Configuração centralizada para todos os módulos de análise forense.
    
    Attributes:
        deepfake_noise_threshold: Limiar de sensibilidade a ruído para detecção
            de splicing (10-90). Valores mais altos = mais sensível.
        deepfake_jitter_threshold: Sensibilidade para instabilidade temporal
            em vídeos (5-50). Valores mais altos = mais tolerante.
        deepfake_fast_mode: Se True, pula análises pesadas (FFT/LBP frame-a-frame).
        copymove_features: Número máximo de features SIFT para detecção de copy-move.
        copymove_min_cluster: Mínimo de matches para considerar um cluster válido.
        resampling_block_size: Tamanho do bloco para análise de resampling.
        ela_quality: Qualidade JPEG para ELA (Error Level Analysis).
        prnu_frame_limit: Limite de frames para extração de PRNU.
        scene_threshold: Limiar de detecção de cortes (0.0 a 1.0).
    
    Example:
        >>> config = AnalysisConfig(deepfake_fast_mode=True)
        >>> config.to_dict()
        {'deepfake_noise_threshold': 50, 'deepfake_fast_mode': True, ...}
    """
    
    # Deepfake Analysis
    deepfake_noise_threshold: int = 50
    deepfake_jitter_threshold: int = 15
    deepfake_fast_mode: bool = False
    
    # Image Forensics
    copymove_features: int = 2000
    copymove_min_cluster: int = 4
    resampling_block_size: int = 64
    ela_quality: int = 90
    
    # Video/PRNU Analysis
    prnu_frame_limit: int = 50
    scene_threshold: float = 0.3
    
    # Report Generation
    report_gop: bool = True
    report_benford: bool = True
    report_prnu: bool = True
    report_quantization: bool = True
    report_scdet: bool = True
    report_timestamps: bool = True
    report_structure: bool = True
    report_deepfake: bool = True
    
    # Image Report
    report_ela: bool = True
    report_noise: bool = True
    report_copymove: bool = True
    report_resampling: bool = True
    report_jpeg_ghosts: bool = True
    
    # Audio Forensics
    audio_noise_window: float = 0.5  # Janela em segundos para análise de ruído
    audio_silence_threshold: float = -60.0  # dB para considerar silêncio
    audio_segment_duration: float = 20.0  # Segundos por segmento (X)
    audio_random_segments: int = 3  # Quantidade de segmentos aleatórios no meio (N)
    audio_silence_margin_seconds: float = 1.0  # Margem para ignorar zeros no início/fim da gravação
    
    # Audio Report
    report_audio_metadata: bool = True
    report_audio_spectral: bool = True
    report_audio_phase: bool = True
    report_audio_silence: bool = True
    report_audio_deepfake: bool = True
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnalysisConfig":
        """Cria configuração a partir de dicionário.
        
        Ignora chaves que não existem na dataclass, permitindo
        compatibilidade com configurações antigas.
        
        Args:
            data: Dicionário com valores de configuração.
            
        Returns:
            Nova instância de AnalysisConfig.
        """
        valid_fields = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)
    
    @classmethod
    def from_json_file(cls, path: Path) -> "AnalysisConfig":
        """Carrega configuração de arquivo JSON.
        
        Args:
            path: Caminho para o arquivo JSON.
            
        Returns:
            Nova instância de AnalysisConfig.
            
        Raises:
            FileNotFoundError: Se o arquivo não existir.
            json.JSONDecodeError: Se o JSON for inválido.
        """
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)
    
    def to_dict(self) -> dict[str, Any]:
        """Exporta configuração para dicionário.
        
        Returns:
            Dicionário com todos os campos da configuração.
        """
        return asdict(self)
    
    def save_to_json(self, path: Path) -> None:
        """Salva configuração em arquivo JSON.
        
        Args:
            path: Caminho para o arquivo de destino.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)


# Instância padrão para uso global
DEFAULT_CONFIG = AnalysisConfig()
