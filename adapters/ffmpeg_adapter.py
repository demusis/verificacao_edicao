import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core.logger import Logger
from core.subprocess_utils import DEFAULT_TIMEOUT, LONG_TIMEOUT, run_command


class FFmpegAdapter:
    """Wrapper para execução segura e auditada do FFmpeg/FFprobe."""

    def __init__(self, logger: Logger | None = None):
        self.logger = logger
        self.ffmpeg_path = shutil.which("ffmpeg")
        self.ffprobe_path = shutil.which("ffprobe")

        if not self.ffmpeg_path or not self.ffprobe_path:
            # Em produção, poderíamos tratar melhor ou buscar em caminhos locais
            if self.logger:
                self.logger.log("ERROR", {"msg": "Binários do FFmpeg não encontrados"})
            raise RuntimeError("FFmpeg/FFprobe não encontrados no PATH do sistema. Instale o FFmpeg.")

    def get_version(self) -> dict[str, str]:
        """Retorna versão do FFmpeg e FFprobe."""
        try:
            res = run_command([self.ffmpeg_path, "-version"], timeout=30)
            version_line = res.stdout.split('\n')[0]
            return {"ffmpeg_version": version_line}
        except Exception as e:
            if self.logger:
                self.logger.log("ERROR", {"msg": f"Erro ao obter versão: {e!s}"})
            return {"error": str(e)}

    def probe_file(self, filepath: Path) -> dict[str, Any]:
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

            res = run_command(cmd, check=True, timeout=DEFAULT_TIMEOUT)
            data = json.loads(res.stdout)
            return data
        except subprocess.TimeoutExpired as e:
            if self.logger:
                self.logger.log("EXEC_ERROR", {"msg": f"FFprobe excedeu timeout: {e}"})
            raise RuntimeError(f"FFprobe excedeu o tempo limite ao analisar {filepath}") from e
        except subprocess.CalledProcessError as e:
            error_msg = f"FFprobe falhou: {e.stderr}"
            if self.logger:
                self.logger.log("EXEC_ERROR", {"stderr": e.stderr})
            raise RuntimeError(error_msg) from e
        except json.JSONDecodeError as e:
            raise RuntimeError("Falha ao decodificar saída do FFprobe.") from e

    def extract_gop_structure(self, filepath: Path) -> list[dict[str, Any]]:
        """Extrai estrutura GOP (I/P/B frames). Custo alto para vídeos longos."""
        # pkt_pts_time foi removido no ffmpeg 5+ (virou pts_time); pedimos
        # ambos para manter compatibilidade entre versões.
        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "frame=pict_type,pts_time,pkt_pts_time",
            "-of", "json",
            str(filepath)
        ]

        # TODO: Implementar chunking ou leitura streamada para arquivos grandes
        # Por enquanto lemos tudo (Cuidado com memória no MVP)
        try:
            if self.logger:
                self.logger.log("EXEC_COMMAND", {"command": " ".join(cmd)})

            res = run_command(cmd, check=True, timeout=LONG_TIMEOUT)
            data = json.loads(res.stdout)
            return data.get("frames", [])
        except Exception as e:
            if self.logger:
                self.logger.log("EXEC_ERROR", {"msg": str(e)})
            raise

    def extract_frame_sizes(self, filepath: Path) -> dict[str, Any]:
        """Extrai o tamanho em bytes de cada frame para análise estatística (Benford/Fourier)."""
        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries",
            "frame=pict_type,pkt_size,pts_time,pkt_pts_time,pkt_dts_time",
            "-of", "json",
            str(filepath)
        ]

        try:
            if self.logger:
                self.logger.log("EXEC_COMMAND", {"command": " ".join(cmd)})

            res = run_command(cmd, check=True, timeout=LONG_TIMEOUT)
            data = json.loads(res.stdout)

            sizes = {"all": [], "I": [], "P": [], "B": [], "packets": []}
            for f in data.get("frames", []):
                s = self._safe_int(f.get("pkt_size", 0))
                t = f.get("pict_type", "?") # I, P, B

                # Timestamp em segundos; ffmpeg 5+ usa pts_time, versões
                # antigas usavam pkt_pts_time.
                pts_val = self._safe_float(f.get("pts_time", f.get("pkt_pts_time")))
                dts_val = self._safe_float(f.get("pkt_dts_time"))

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
                self.logger.log("EXEC_ERROR", {"msg": f"Erro extracting frame sizes: {e!s}"})
            return {"all": [], "I": [], "P": [], "B": [], "packets": []}

    @staticmethod
    def _safe_int(value: Any) -> int:
        """Converte valor do ffprobe para int, tolerando 'N/A'/None."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        """Converte valor do ffprobe para float, tolerando 'N/A'/None."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
