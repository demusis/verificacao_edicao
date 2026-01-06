from pathlib import Path
import json
import subprocess
import re
from core.case_manager import CaseManager

class QuantizationAnalysisModule:
    """
    Análise de Quantização (Q-Matrices e QP).
    Objetivo: Identificar assinaturas de encoder e qualidade de compressão.
    """
    
    def __init__(self, case_manager: CaseManager):
        self.cm = case_manager
        self.logger = self.cm.get_logger()
        
    def run(self, input_file: Path, output_filename: str = "quantization_analysis.json"):
        self.logger.log("QUANT_START", {"file": input_file.name})
        
        try:
            # 1. Análise de Q-Matrices (Scaling Lists no H.264)
            q_matrix_info = self._analyze_q_matrices(input_file)
            
            # 2. Histograma QP (Estimativa de qualidade média)
            qp_stats = self._extract_qp_stats(input_file)
            
            # 3. Calcular Bits Per Pixel (BPP)
            bpp_data = self._calculate_bpp(input_file)
            
            result = {
                "q_matrix_info": q_matrix_info,
                "qp_stats": qp_stats,
                "bpp_info": bpp_data
            }
            
            # Conclusão preliminar
            result["conclusion"] = self._generate_conclusion(result)

            out_path = self.cm.results_dir / output_filename
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=4)
                
            self.logger.log("QUANT_SUCCESS", {"file": input_file.name})
            return result
            
        except Exception as e:
            self.logger.log("QUANT_ERROR", {"error": str(e)})
            return {"error": str(e)}

    def _analyze_q_matrices(self, input_file: Path) -> dict:
        """
        Usa bitstream filter 'trace_headers' para verificar presença de scaling lists customizadas.
        Custom Scaling Lists são comuns em encoders otimizados (x264 high profile) ou câmeras específicas.
        Scaling Lists ausentes (flat) são comuns em compressões rápidas/padrão.
        Adicionalmente, extrai Refs Frames, Scan Type e CABAC/CAVLC.
        """
        # ffmpeg -i input -c:v copy -bsf:v trace_headers -f null - 
        # Output vai para stderr.
        # Limitamos a leitura a alguns frames para não demorar.
        
        cmd = [
            "ffmpeg", "-v", "verbose",
            "-i", str(input_file),
            "-c:v", "copy",
            "-bsf:v", "trace_headers",
            "-frames:v", "20", # Aumentado para 20 para garantir captura de PPS
            "-f", "null", "-"
        ]
        
        try:
            # Precisamos capturar STDERR
            res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            log = res.stderr
            
            # Parser simplificado
            found_sps = "seq_parameter_set_rbsp" in log
            
            # --- Scaling Matrices ---
            has_custom_matrix = False
            if "seq_scaling_matrix_present_flag" in log:
                # Procura o valor
                # Ex: seq_scaling_matrix_present_flag[   1]
                match = re.search(r"seq_scaling_matrix_present_flag\s*.*?(\d)", log)
                if match and match.group(1) == '1':
                    has_custom_matrix = True
            
            # --- Profile ---
            profile = "Unknown"
            match_prof = re.search(r"profile_idc\s*.*?(\d+)", log)
            if match_prof:
                pidc = int(match_prof.group(1))
                if pidc == 66: profile = "Baseline"
                elif pidc == 77: profile = "Main"
                elif pidc == 100: profile = "High"
            
            # --- Reference Frames ---
            # num_ref_frames usually appears in SPS log
            # num_ref_frames[   4]  (example)
            num_ref_frames = 0
            match_ref = re.search(r"num_ref_frames\s+.*?(\d+)", log)
            if match_ref:
                num_ref_frames = int(match_ref.group(1))
            
            # --- Scan Type (Progressive vs Interlaced) ---
            # frame_mbs_only_flag: 1 -> Progressive, 0 -> Interlaced (PAFF/MBAFF)
            scan_type = "Unknown"
            match_scan = re.search(r"frame_mbs_only_flag\s+.*?(\d)", log)
            if match_scan:
                val = int(match_scan.group(1))
                scan_type = "Progressivo" if val == 1 else "Entrelaçado"
            
            # --- Entropy Coding (CABAC/CAVLC) ---
            # entropy_coding_mode_flag in PPS. 0 -> CAVLC, 1 -> CABAC
            # Only present in Main/High profiles usually.
            entropy = "N/A"
            if "pic_parameter_set_rbsp" in log:
                match_ent = re.search(r"entropy_coding_mode_flag\s+.*?(\d)", log)
                if match_ent:
                    val = int(match_ent.group(1))
                    entropy = "CABAC" if val == 1 else "CAVLC"
            
            return {
                "sps_found": found_sps,
                "has_custom_scaling_matrix": has_custom_matrix,
                "profile_idc": profile,
                "num_ref_frames": num_ref_frames,
                "scan_type": scan_type,
                "entropy_coding": entropy,
                "trace_snippet": log[:500] if found_sps else "No SPS found in trace"
            }
            
        except Exception as e:
            return {"error": f"Trace failed: {str(e)}"}

    def _calculate_bpp(self, input_file: Path) -> dict:
        """
        Calcula bits-per-pixel.
        BPP = Bitrate / (Width * Height * FPS)
        Baixo BPP (<0.1) -> Baixa qualidade/Alta compressão.
        Alto BPP (>0.2) -> Boa qualidade.
        """
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,avg_frame_rate,bit_rate",
                "-of", "json",
                str(input_file)
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(res.stdout)
            stream = data.get('streams', [{}])[0]
            
            w = int(stream.get('width', 0))
            h = int(stream.get('height', 0))
            br_str = stream.get('bit_rate', '0')
            fps_str = stream.get('avg_frame_rate', '0/0')
            
            # FPS parser
            if '/' in fps_str:
                num, den = map(int, fps_str.split('/'))
                fps = num / den if den != 0 else 0
            else:
                fps = float(fps_str)
                
            bitrate = int(br_str) if br_str != 'N/A' else 0
            
            bpp = 0.0
            if w > 0 and h > 0 and fps > 0:
                pixel_count = w * h
                bpp = bitrate / (pixel_count * fps)
                
            return {
                "bpp": round(bpp, 4),
                "resolution": f"{w}x{h}",
                "fps": round(fps, 3),
                "bitrate_kbps": round(bitrate / 1000, 1)
            }
        except Exception as e:
            return {"error": str(e), "bpp": 0}

    def _extract_qp_stats(self, input_file: Path) -> dict:
        """
        Estima QP médio.
        Método: 'qp' filter ou 'debug=qp'. 
        O filtro 'qp' é complexo de parsear visualmente.
        Filtro 'signalstats' não dá QP diretamente.
        Filtro 'ppb' ou 'codecview' com 'qp' desenha na tela.
        
        Melhor método scriptável sem re-encode: debug vector info ou packet params.
        
        Método alternativo rápido: Usar ffprobe para ler 'pkt_size' e 'duration' e estimar BPP,
        mas o QP real exige decode.
        
        Vamos tentar o 'debug' flag do encoder? Não, estamos decodificando.
        
        Solução Robusta: Usar packet analysis em profundidade.
        Mas para este MVP, vamos usar uma heurística simples baseada no Bitrate vs Resolução (Bits/(Pixel*Frame)),
        Ou tentar capturar do log de debug se o ffmpeg printar.
        
        Vamos assumir QP médio estimado pelo Bitrate por enquanto se não conseguirmos extrair.
        
        Tentativa com filtro 'qp' (libpostproc) se existir? Não é padrão.
        
        Vamos deixar 'Not Available' para QP real neste MVP e focar na Q-Matrix que é a assinatura pedida.
        """
        return {"status": "Non-trivial without full decode parse"}

    def _generate_conclusion(self, data: dict) -> str:
        q = data.get("q_matrix_info", {})
        has_custom = q.get("has_custom_scaling_matrix", False)
        profile = q.get("profile_idc", "Unknown")
        
        bpp_info = data.get("bpp_info", {})
        bpp = bpp_info.get("bpp", 0)
        
        parts = []
        
        # Scaling Matrix
        if has_custom:
            parts.append(f"Matrizes Customizadas (Profile {profile}), típico de encoders avançados.")
        else:
            parts.append(f"Matrizes Padrão/Flat (Profile {profile}).")
            
        # Ref Frames
        refs = q.get("num_ref_frames", 0)
        if refs > 4:
            parts.append(f"Alto uso de quadros de referência ({refs}), indicando foco em compressão (Longo GOP).")
        
        # BPP
        if bpp > 0:
            if bpp < 0.1:
                qual_est = "baixa densidade (alta compressão)"
            elif bpp > 0.25:
                qual_est = "alta densidade (baixa compressão)"
            else:
                qual_est = "densidade média"
            parts.append(f"BPP de {bpp:.3f} indica {qual_est}.")
            
        return " ".join(parts)
