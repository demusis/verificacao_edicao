from pathlib import Path
import json
import re
import subprocess
from core.case_manager import CaseManager
from adapters.ffmpeg_adapter import FFmpegAdapter

class ContinuityModule:
    """Módulo de análise de continuidade visual (Detecção de Cortes)."""
    
    def __init__(self, case_manager: CaseManager):
        self.cm = case_manager
        self.logger = self.cm.get_logger()
        self.ffmpeg = FFmpegAdapter(self.logger)

    def run(self, input_file: Path, threshold: float = 0.3, output_filename: str = "continuity_analysis.json"):
        self.logger.log("START_MODULE", {"module": "ContinuityAnalysis", "file": str(input_file)})
        
        try:
            # Detecção de mudança de cena (Scene Change Detection - SCDET)
            # threshold: diferença entre frames (0 a 100). 
            # ffmpeg usa filtro scdet ou select='gt(scene,X)'
            
            self.logger.log("SCENE_DETECT_START", {"threshold": threshold})
            
            # Comando para obter scores de cena
            # showinfo gera log no stderr
            cmd = [
                self.ffmpeg.ffmpeg_path,
                "-v", "info", # precisa ser info para ver o showinfo
                "-i", str(input_file),
                "-vf", f"select='gt(scene,{threshold})',showinfo",
                "-f", "null",
                "-"
            ]
            
            self.logger.log("EXEC_COMMAND", {"command": " ".join(cmd)})
            res = subprocess.run(cmd, capture_output=True, text=True)
            
            # Parsear saída do showinfo (stderr)
            # Ex: [Parsed_showinfo_1 @ ...] n:   0 pts:  120120 pts_time:4.004  ...
            cuts = []
            
            # Regex simples para extrair pts_time
            # n:\s*(\d+)\s+pts:\s*(\d+)\s+pts_time:([\d\.]+)
            pattern = re.compile(r"n:\s*(\d+)\s+pts:\s*(\d+)\s+pts_time:([\d\.]+)")
            
            for line in res.stderr.split('\n'):
                if "pts_time" in line and "Parsed_showinfo" in line:
                    match = pattern.search(line)
                    if match:
                        cuts.append({
                            "frame_n": int(match.group(1)),
                            "pts": int(match.group(2)),
                            "timestamp": float(match.group(3))
                        })
            
            self.logger.log("SCENE_DETECT_END", {"cuts_found": len(cuts)})
            
            # 2. Análise Temporal (PTS/DTS)
            self.logger.log("TIMESTAMP_ANALYSIS_START")
            ts_anomalies = self._analyze_timestamps(input_file)
            self.logger.log("TIMESTAMP_ANALYSIS_END", {"anomalies": len(ts_anomalies)})
            
            result_data = {
                "cuts_detected": cuts,
                "total_cuts": len(cuts),
                "timestamp_anomalies": ts_anomalies
            }
            
            output_file = self.cm.results_dir / output_filename
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, indent=2, ensure_ascii=False)
                
            self.logger.log("MODULE_SUCCESS", {"module": "ContinuityAnalysis", "output": str(output_file)})
            
        except Exception as e:
            self.logger.log("MODULE_ERROR", {"module": "ContinuityAnalysis", "error": str(e)})
            raise

    def _analyze_timestamps(self, input_file: Path) -> list:
        """Verifica linearidade e monotocidade dos timestamps."""
        data = self.ffmpeg.extract_frame_sizes(input_file)
        packets = data.get("packets", [])
        
        anomalies = []
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
            deltas = []
            for i in range(1, len(sorted_pts)):
                d = sorted_pts[i]['pts'] - sorted_pts[i-1]['pts']
                deltas.append(d)
                
            avg_delta = sum(deltas) / len(deltas) if deltas else 0
            
            # Threshold para Gap: > 10x frame duration médio (evita falsos positivos em VFR leve)
            # Ou fixo > 0.5s? Usar média heurística.
            gap_threshold = max(2.0 * avg_delta, 0.1) 
            
            for i in range(1, len(sorted_pts)):
                delta = deltas[i-1]
                if delta > gap_threshold:
                     anomalies.append({
                        "type": "Visual Gap (PTS)",
                        "timestamp": sorted_pts[i-1]['pts'],
                        "message": f"Salto temporal visual de {delta:.3f}s (Média: {avg_delta:.3f}s)"
                     })

        return anomalies
