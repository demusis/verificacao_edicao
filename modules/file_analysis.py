from pathlib import Path
import json
from core.case_manager import CaseManager
from core.hashing import calculate_file_hash
from adapters.ffmpeg_adapter import FFmpegAdapter

class FileAnalysisModule:
    """Módulo de análise básica de arquivo: Hash, Metadados e GOP."""
    
    def __init__(self, case_manager: CaseManager):
        self.cm = case_manager
        self.logger = self.cm.get_logger()
        self.ffmpeg = FFmpegAdapter(self.logger)

    def run(self, input_file: Path, output_filename: str = "file_analysis.json"):
        self.logger.log("START_MODULE", {"module": "FileAnalysis", "file": str(input_file)})
        
        try:
            # 1. Cálculo de Hash do Arquivo (Integridade)
            self.logger.log("HASH_CALC_START", {"algorithm": "sha512"})
            file_hash = calculate_file_hash(input_file)
            self.logger.log("HASH_CALC_END", {"hash": file_hash})
            
            # 2. Extração de Metadados (Container)
            self.logger.log("METADATA_EXTRACT_START")
            metadata = self.ffmpeg.probe_file(input_file)
            self.logger.log("METADATA_EXTRACT_END")
            
            # 3. Análise de GOP (Simplificada)
            self.logger.log("GOP_ANALYSIS_START")
            gop_frames = self.ffmpeg.extract_gop_structure(input_file)
            
            # Estatísticas GOP
            i_frames = [f for f in gop_frames if f.get("pict_type") == "I"]
            p_frames = [f for f in gop_frames if f.get("pict_type") == "P"]
            b_frames = [f for f in gop_frames if f.get("pict_type") == "B"]
            
            gop_stats = {
                "total_frames_analyzed": len(gop_frames),
                "i_frames": len(i_frames),
                "p_frames": len(p_frames),
                "b_frames": len(b_frames),
                "avg_gop_size": len(gop_frames) / len(i_frames) if i_frames else 0
            }
            self.logger.log("GOP_ANALYSIS_END", gop_stats)
            
            # 4. Análise de Indícios de Processamento (Double Encoding)
            processing_traces = self._analyze_processing_traces(metadata)
            
            # 5. Salvar Resultados
            result_data = {
                "file_hash": file_hash,
                "metadata": metadata,
                "gop_stats": gop_stats,
                "processing_analysis": processing_traces,
                "gop_structure": gop_frames
            }
            
            output_file = self.cm.results_dir / output_filename
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, indent=2, ensure_ascii=False)
                
            self.logger.log("MODULE_SUCCESS", {"module": "FileAnalysis", "output": str(output_file)})
            
        except Exception as e:
            self.logger.log("MODULE_ERROR", {"module": "FileAnalysis", "error": str(e)})
            raise

    def _analyze_processing_traces(self, metadata: dict) -> dict:
        """Busca traços de softwares de edição/transcodificação nos metadados."""
        traces = []
        suspicious_keywords = [
            'Lavf', 'HandBrake', 'Adobe', 'Premiere', 'Vegas', 'CapCut', 
            'DaVinci', 'ffmpeg', 'libx264', 'Isom', 'OpenShot'
        ]
        
        # Helper para checar dicionário de tags
        def check_tags(tags, source):
            if not tags: return
            for k, v in tags.items():
                v_str = str(v)
                for keyword in suspicious_keywords:
                    if keyword.lower() in v_str.lower():
                        traces.append({
                            "source": source,
                            "key": k,
                            "value": v_str,
                            "keyword_match": keyword
                        })

        # 1. Checar Container Tags
        fmt = metadata.get('format', {})
        check_tags(fmt.get('tags', {}), "Container Format")
        
        # 2. Checar encoder field explícito do FFprobe (se houver)
        # Às vezes aparece fora das tags dependendo da versão
        
        # 3. Checar Streams Tags
        for stream in metadata.get('streams', []):
            idx = stream.get('index', '?')
            check_tags(stream.get('tags', {}), f"Stream #{idx}")

        return {
            "detected": len(traces) > 0,
            "traces_found": traces,
            "conclusion": "Indícios de reprocessamento por software detectados." if traces else "Nenhuma assinatura óbvia de software de edição conhecida encontrada."
        }
