"""
Módulo de análise de continuidade visual.

Detecta cortes de edição e anomalias temporais em vídeos através
de análise de cena e verificação de timestamps PTS/DTS.
"""
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from adapters.ffmpeg_adapter import FFmpegAdapter
from core.case_manager import CaseManager
from core.config_schema import AnalysisConfig
from core.subprocess_utils import LONG_TIMEOUT, run_command


class ContinuityModule:
    """Módulo de análise de continuidade visual (Detecção de Cortes).
    
    Implementa detecção de mudanças de cena e análise de linearidade
    dos timestamps de apresentação (PTS) e decodificação (DTS).
    
    Attributes:
        MODULE_NAME: Identificador do módulo para logs.
        cm: Gerenciador de caso.
        config: Configuração de análise.
        logger: Logger para auditoria.
        ffmpeg: Adaptador FFmpeg para processamento.
    """
    
    MODULE_NAME: str = "ContinuityAnalysis"
    
    def __init__(
        self,
        case_manager: CaseManager,
        config: AnalysisConfig | None = None
    ) -> None:
        """Inicializa o módulo de continuidade.
        
        Args:
            case_manager: Gerenciador de caso para diretórios e logs.
            config: Configuração opcional de análise.
        """
        self.cm = case_manager
        self.config = config or AnalysisConfig()
        self.logger = self.cm.get_logger()
        self.ffmpeg = FFmpegAdapter(self.logger)
    
    def run(
        self,
        input_file: Path,
        threshold: float | None = None,
        output_filename: str = "continuity_analysis.json",
        progress_callback: Callable[[str], None] | None = None
    ) -> dict[str, Any]:
        """Executa análise de continuidade no vídeo.
        
        Args:
            input_file: Caminho do arquivo de vídeo.
            threshold: Limiar de detecção de cortes (0.0-1.0).
                      Se None, usa config.scene_threshold.
            output_filename: Nome do arquivo de saída.
            progress_callback: Callback para progresso.
            
        Returns:
            Dicionário com cortes detectados e anomalias.
            
        Raises:
            RuntimeError: Se FFmpeg falhar.
        """
        if threshold is None:
            threshold = self.config.scene_threshold
        
        self.logger.log("START_MODULE", {
            "module": self.MODULE_NAME,
            "file": str(input_file)
        })
        
        try:
            # 1. Detecção de mudança de cena
            if progress_callback:
                progress_callback("Detectando cortes de cena...")
            
            self.logger.log("SCENE_DETECT_START", {"threshold": threshold})
            cuts = self._detect_scene_changes(input_file, threshold)
            self.logger.log("SCENE_DETECT_END", {"cuts_found": len(cuts)})
            
            # 2. Análise de timestamps
            if progress_callback:
                progress_callback("Analisando timestamps PTS/DTS...")
            
            self.logger.log("TIMESTAMP_ANALYSIS_START")
            ts_anomalies = self._analyze_timestamps(input_file)
            self.logger.log("TIMESTAMP_ANALYSIS_END", {"anomalies": len(ts_anomalies)})
            
            # 3. Montar resultado
            result_data = {
                "cuts_detected": cuts,
                "total_cuts": len(cuts),
                "timestamp_anomalies": ts_anomalies,
                "threshold_used": threshold
            }
            
            # 4. Salvar
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
    
    def _detect_scene_changes(
        self,
        input_file: Path,
        threshold: float
    ) -> list[dict[str, Any]]:
        """Detecta mudanças de cena usando filtro FFmpeg.
        
        Args:
            input_file: Arquivo de vídeo.
            threshold: Limiar de detecção (0.0-1.0).
            
        Returns:
            Lista de cortes detectados com frame, pts e timestamp.
        """
        cmd = [
            self.ffmpeg.ffmpeg_path,
            "-v", "info",
            "-i", str(input_file),
            "-vf", f"select='gt(scene,{threshold})',showinfo",
            "-f", "null",
            "-"
        ]
        
        self.logger.log("EXEC_COMMAND", {"command": " ".join(cmd)})
        result = run_command(cmd, timeout=LONG_TIMEOUT)

        cuts: list[dict[str, Any]] = []
        pattern = re.compile(r"n:\s*(\d+)\s+pts:\s*(\d+)\s+pts_time:([\d\.]+)")

        showinfo_lines = 0
        for line in result.stderr.split('\n'):
            if "pts_time" in line and "Parsed_showinfo" in line:
                showinfo_lines += 1
                match = pattern.search(line)
                if match:
                    cuts.append({
                        "frame_n": int(match.group(1)),
                        "pts": int(match.group(2)),
                        "timestamp": float(match.group(3))
                    })

        # Se o showinfo produziu linhas mas nenhuma casou com a regex, o
        # formato de saída do ffmpeg provavelmente mudou — registrar para
        # não mascarar como "zero cortes detectados".
        if showinfo_lines and not cuts:
            self.logger.log("SCENE_DETECT_WARNING", {
                "msg": "Saída do showinfo não reconhecida pela regex",
                "showinfo_lines": showinfo_lines
            })

        return cuts
    
    def _analyze_timestamps(self, input_file: Path) -> list[dict[str, Any]]:
        """Verifica linearidade e monotonicidade dos timestamps.
        
        Detecta:
        - DTS Backjumps: timestamps de decodificação não-monotônicos
        - PTS Gaps: saltos visuais anormais na apresentação
        
        Args:
            input_file: Arquivo de vídeo.
            
        Returns:
            Lista de anomalias encontradas.
        """
        data = self.ffmpeg.extract_frame_sizes(input_file)
        packets = data.get("packets", [])
        
        anomalies: list[dict[str, Any]] = []
        if not packets:
            return anomalies
        
        # 1. DTS Monotonicity (Decoding Order)
        last_dts = -float('inf')
        for pkt in packets:
            dts = pkt.get('dts')
            if dts is not None:
                if dts < last_dts:
                    anomalies.append({
                        "type": "DTS Backjump",
                        "timestamp": dts,
                        "message": f"DTS retrocedeu de {last_dts} para {dts}"
                    })
                last_dts = dts
        
        # 2. PTS Linearity (Display Order) - Gaps
        valid_pts = [p for p in packets if p.get('pts') is not None]
        sorted_pts = sorted(valid_pts, key=lambda x: x['pts'])
        
        if len(sorted_pts) > 1:
            deltas: list[float] = []
            for i in range(1, len(sorted_pts)):
                d = sorted_pts[i]['pts'] - sorted_pts[i-1]['pts']
                deltas.append(d)
            
            avg_delta = sum(deltas) / len(deltas) if deltas else 0
            gap_threshold = max(2.0 * avg_delta, 0.1)
            
            for i in range(1, len(sorted_pts)):
                delta = deltas[i-1]
                if delta > gap_threshold:
                    anomalies.append({
                        "type": "Visual Gap (PTS)",
                        "timestamp": sorted_pts[i-1]['pts'],
                        "message": f"Salto temporal de {delta:.3f}s (Média: {avg_delta:.3f}s)"
                    })
        
        return anomalies
