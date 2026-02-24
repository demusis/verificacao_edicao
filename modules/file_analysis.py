"""
Módulo de análise básica de arquivo.

Extrai hash de integridade, metadados do container, estrutura GOP
e detecta indícios de processamento/edição.
"""
import json
from pathlib import Path
from typing import Any, Callable, Optional

from core.case_manager import CaseManager
from core.config_schema import AnalysisConfig
from core.hashing import calculate_file_hash
from adapters.ffmpeg_adapter import FFmpegAdapter


class FileAnalysisModule:
    """Módulo de análise básica de arquivo: Hash, Metadados e GOP.
    
    Executa as análises fundamentais para qualquer arquivo de mídia:
    - Hash SHA-512 para integridade
    - Metadados do container via FFprobe
    - Estrutura GOP para vídeos
    - Detecção de traces de software de edição
    
    Attributes:
        MODULE_NAME: Identificador do módulo.
        cm: Gerenciador de caso.
        config: Configuração de análise.
        logger: Logger para auditoria.
        ffmpeg: Adaptador FFmpeg.
    """
    
    MODULE_NAME: str = "FileAnalysis"
    
    # Keywords que indicam processamento por software
    PROCESSING_KEYWORDS: tuple[str, ...] = (
        'Lavf', 'HandBrake', 'Adobe', 'Premiere', 'Vegas', 'CapCut',
        'DaVinci', 'ffmpeg', 'libx264', 'Isom', 'OpenShot', 'After Effects',
        'Final Cut', 'Avid', 'Sony', 'encoder'
    )
    
    def __init__(
        self,
        case_manager: CaseManager,
        config: Optional[AnalysisConfig] = None
    ) -> None:
        """Inicializa o módulo de análise de arquivo.
        
        Args:
            case_manager: Gerenciador de caso.
            config: Configuração opcional.
        """
        self.cm = case_manager
        self.config = config or AnalysisConfig()
        self.logger = self.cm.get_logger()
        self.ffmpeg = FFmpegAdapter(self.logger)
    
    def run(
        self,
        input_file: Path,
        output_filename: str = "file_analysis.json",
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> dict[str, Any]:
        """Executa análise básica do arquivo.
        
        Args:
            input_file: Arquivo a ser analisado.
            output_filename: Nome do arquivo de saída.
            progress_callback: Callback para progresso.
            
        Returns:
            Dicionário com hash, metadados, GOP e traces.
        """
        self.logger.log("START_MODULE", {
            "module": self.MODULE_NAME,
            "file": str(input_file)
        })
        
        try:
            # 1. Hash de integridade
            if progress_callback:
                progress_callback("Calculando hash SHA-512...")
            
            self.logger.log("HASH_CALC_START", {"algorithm": "sha512"})
            file_hash = calculate_file_hash(input_file)
            self.logger.log("HASH_CALC_END", {"hash": file_hash})
            
            # 2. Metadados do container
            if progress_callback:
                progress_callback("Extraindo metadados...")
            
            self.logger.log("METADATA_EXTRACT_START")
            metadata = self.ffmpeg.probe_file(input_file)
            
            if not metadata or not metadata.get("format"):
                self.logger.log("METADATA_EXTRACT_WARNING", {
                    "msg": "Metadados vazios ou incompletos"
                })
            else:
                self.logger.log("METADATA_EXTRACT_END", {
                    "format_keys": list(metadata["format"].keys())
                })
            
            # 3. Análise GOP
            if progress_callback:
                progress_callback("Analisando estrutura GOP...")
            
            self.logger.log("GOP_ANALYSIS_START")
            gop_frames = self.ffmpeg.extract_gop_structure(input_file)
            gop_stats = self._calculate_gop_stats(gop_frames)
            self.logger.log("GOP_ANALYSIS_END", gop_stats)
            
            # 4. Traces de processamento
            if progress_callback:
                progress_callback("Verificando indícios de edição...")
            
            processing_traces = self._analyze_processing_traces(metadata)
            
            # 5. Montar e salvar resultado
            result_data = {
                "file_hash": file_hash,
                "metadata": metadata,
                "gop_stats": gop_stats,
                "processing_analysis": processing_traces,
                "gop_structure": gop_frames
            }
            
            output_path = self.cm.results_dir / output_filename
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, indent=2, ensure_ascii=False)
            
            self.logger.log("MODULE_SUCCESS", {
                "module": self.MODULE_NAME,
                "output": str(output_path)
            })
            
            return result_data
            
        except Exception as e:
            self.logger.log("MODULE_ERROR", {
                "module": self.MODULE_NAME,
                "error": str(e)
            })
            raise
    
    def _calculate_gop_stats(
        self,
        gop_frames: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Calcula estatísticas da estrutura GOP.
        
        Args:
            gop_frames: Lista de frames com pict_type.
            
        Returns:
            Estatísticas: contagem de I/P/B frames e GOP médio.
        """
        i_frames = [f for f in gop_frames if f.get("pict_type") == "I"]
        p_frames = [f for f in gop_frames if f.get("pict_type") == "P"]
        b_frames = [f for f in gop_frames if f.get("pict_type") == "B"]
        
        total = len(gop_frames)
        i_count = len(i_frames)
        
        return {
            "total_frames_analyzed": total,
            "i_frames": i_count,
            "p_frames": len(p_frames),
            "b_frames": len(b_frames),
            "avg_gop_size": total / i_count if i_count > 0 else total if total > 0 else 0
        }
    
    def _analyze_processing_traces(
        self,
        metadata: dict[str, Any]
    ) -> dict[str, Any]:
        """Busca traces de software de edição nos metadados.
        
        Args:
            metadata: Metadados do FFprobe.
            
        Returns:
            Análise com traces encontrados e conclusão.
        """
        traces: list[dict[str, str]] = []
        
        def check_tags(tags: Optional[dict], source: str) -> None:
            if not tags:
                return
            for key, value in tags.items():
                value_str = str(value)
                for keyword in self.PROCESSING_KEYWORDS:
                    if keyword.lower() in value_str.lower():
                        traces.append({
                            "source": source,
                            "key": key,
                            "value": value_str,
                            "keyword_match": keyword
                        })
        
        # Container tags
        fmt = metadata.get('format', {})
        check_tags(fmt.get('tags'), "Container Format")
        
        # Stream tags
        for stream in metadata.get('streams', []):
            idx = stream.get('index', '?')
            check_tags(stream.get('tags'), f"Stream #{idx}")
        
        return {
            "detected": len(traces) > 0,
            "traces_found": traces,
            "conclusion": (
                "Indícios de reprocessamento por software detectados."
                if traces else
                "Nenhuma assinatura óbvia de software de edição encontrada."
            )
        }
