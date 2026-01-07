import subprocess
import json
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from core.logger import Logger

class FFmpegAdapter:
    """Wrapper para execução segura e auditada do FFmpeg/FFprobe."""
    
    def __init__(self, logger: Optional[Logger] = None):
        self.logger = logger
        self.ffmpeg_path = shutil.which("ffmpeg")
        self.ffprobe_path = shutil.which("ffprobe")
        
        if not self.ffmpeg_path or not self.ffprobe_path:
            # Em produção, poderíamos tratar melhor ou buscar em caminhos locais
            if self.logger:
                self.logger.log("ERROR", {"msg": "Binários do FFmpeg não encontrados"})
            raise RuntimeError("FFmpeg/FFprobe não encontrados no PATH do sistema. Instale o FFmpeg.")

    def get_version(self) -> Dict[str, str]:
        """Retorna versão do FFmpeg e FFprobe."""
        try:
            res = subprocess.run([self.ffmpeg_path, "-version"], capture_output=True, text=True)
            version_line = res.stdout.split('\n')[0]
            return {"ffmpeg_version": version_line}
        except Exception as e:
            if self.logger:
                self.logger.log("ERROR", {"msg": f"Erro ao obter versão: {str(e)}"})
            return {"error": str(e)}

    def probe_file(self, filepath: Path) -> Dict[str, Any]:
        """Extrai metadados completos do arquivo via FFprobe (JSON)."""
        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-find_stream_info",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            "-show_chapters",
            str(filepath)
        ]
        
        try:
            if self.logger:
                self.logger.log("EXEC_COMMAND", {"command": " ".join(cmd)})
                
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(res.stdout)
            return data
        except subprocess.CalledProcessError as e:
            error_msg = f"FFprobe falhou: {e.stderr}"
            if self.logger:
                self.logger.log("EXEC_ERROR", {"stderr": e.stderr})
            raise RuntimeError(error_msg)
        except json.JSONDecodeError:
            raise RuntimeError("Falha ao decodificar saída do FFprobe.")

    def extract_gop_structure(self, filepath: Path) -> List[Dict[str, Any]]:
        """Extrai estrutura GOP (I/P/B frames). Custo alto para vídeos longos."""
        # ffprobe -show_frames -select_streams v:0 ...
        # Limitado para MVP a amostragem ou vídeo inteiro com aviso.
        # Aqui vamos implementar uma versão simplificada que pega tipo de frame.
        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "frame=pict_type,pkt_pts_time",
            "-of", "json",
            str(filepath)
        ]
        
        # TODO: Implementar chunking ou leitura streamada para arquivos grandes
        # Por enquanto lemos tudo (Cuidado com memória no MVP)
        try:
            if self.logger:
                self.logger.log("EXEC_COMMAND", {"command": " ".join(cmd)})
                
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(res.stdout)
            return data.get("frames", [])
        except Exception as e:
            if self.logger:
                self.logger.log("EXEC_ERROR", {"msg": str(e)})
            raise

    def extract_frame_sizes(self, filepath: Path) -> Dict[str, Any]:
        """Extrai o tamanho em bytes de cada frame para análise estatística (Benford/Fourier)."""
        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "frame=pict_type,pkt_size,pkt_pts_time,pkt_dts_time",
            "-of", "json",
            str(filepath)
        ]
        
        try:
            if self.logger:
                self.logger.log("EXEC_COMMAND", {"command": " ".join(cmd)})
                
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(res.stdout)
            
            sizes = {"all": [], "I": [], "P": [], "B": [], "packets": []}
            for f in data.get("frames", []):
                s = int(f.get("pkt_size", 0))
                t = f.get("pict_type", "?") # I, P, B
                
                # Timestamp Extraction (Float seconds)
                pts = f.get("pkt_pts_time")
                dts = f.get("pkt_dts_time")
                pts_val = float(pts) if pts and pts != "N/A" else None
                dts_val = float(dts) if dts and dts != "N/A" else None
                
                packet_info = {
                    "pts": pts_val,
                    "dts": dts_val,
                    "size": s,
                    "type": t
                }
                sizes["packets"].append(packet_info)
                
                if s > 0:
                    sizes["all"].append(s)
                    if t in sizes:
                        sizes[t].append(s)
            return sizes
            
        except Exception as e:
            if self.logger:
                self.logger.log("EXEC_ERROR", {"msg": f"Erro extracting frame sizes: {str(e)}"})
            return {"all": [], "I": [], "P": [], "B": [], "packets": []}
