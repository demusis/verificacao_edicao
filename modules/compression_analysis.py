from pathlib import Path
import json
import numpy as np
from scipy.fft import fft
from typing import Dict, List, Any
from core.case_manager import CaseManager
from adapters.ffmpeg_adapter import FFmpegAdapter

class CompressionAnalysisModule:
    """
    Análise Estatística de Compressão (Double Encoding Detection).
    Utiliza:
    1. Lei de Benford nos tamanhos de quadros.
    2. Análise de Fourier na sequência de tamanhos de quadros para detectar periodicidade anômala.
    """

    def __init__(self, case_manager: CaseManager):
        self.cm = case_manager
        self.logger = self.cm.get_logger()
        self.ffmpeg = FFmpegAdapter(self.logger)

    def run(self, input_file: Path, output_filename: str = "compression_analysis.json"):
        self.logger.log("START_MODULE", {"module": "CompressionAnalysis", "file": str(input_file)})
        
        try:
            # 1. Extrair tamanhos dos frames (bytes) segmentados por tipo
            frame_sizes_dict = self.ffmpeg.extract_frame_sizes(input_file)
            
            # Garante compatibilidade caso o adapter retorne apenas lista (se algo der errado/versoes antigas)
            if isinstance(frame_sizes_dict, list):
                frame_sizes_dict = {"all": frame_sizes_dict}
                
            all_sizes = frame_sizes_dict.get("all", [])
            if not all_sizes:
                 # Falha silenciosa ou erro
                 pass # Warning logging already in adapter

            # 2. Análise de Benford Segmentada
            benford_res = {
                "global": self._analyze_benford(all_sizes),
                "I": self._analyze_benford(frame_sizes_dict.get("I", [])),
                "P": self._analyze_benford(frame_sizes_dict.get("P", [])),
                "B": self._analyze_benford(frame_sizes_dict.get("B", []))
            }
            
            # 3. Análise de Fourier (Detectar GOP patterns / Double Compression anomalies)
            # Fourier é melhor aplicado na sequência completa (all_sizes) para ver a periodicidade do GOP
            fourier_res = self._analyze_fourier(all_sizes)
            
            # Resultado Final
            result_data = {
                "total_frames": len(all_sizes),
                "benford_analysis": benford_res,
                "fourier_analysis": fourier_res,
                # Conclusão baseada no Global ou mais crítica?
                # Vamos passar o resultado 'global' para manter compatibilidade da func _generate_conclusion 
                # ou atualizar a _generate_conclusion também.
                "conclusion": self._generate_conclusion(benford_res["global"], fourier_res)
            }
            
            output_file = self.cm.results_dir / output_filename
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, indent=2, ensure_ascii=False)
                
            self.logger.log("MODULE_SUCCESS", {"module": "CompressionAnalysis", "conclusion": result_data['conclusion']})
            
        except Exception as e:
            self.logger.log("MODULE_ERROR", {"module": "CompressionAnalysis", "error": str(e)})
            # Não dar raise para não parar o pipeline inteiro se falhar (é módulo avançado)
            # Mas para debug vamos printar
            print(f"Erro no módulo de Compressão: {e}")

    def _analyze_benford(self, sizes: List[int]) -> Dict[str, Any]:
        """Calcula a conformidade com a Lei de Benford (Primeiro Dígito)."""
        # Extrair primeiro dígito
        first_digits = [int(str(s)[0]) for s in sizes if s > 0]
        total = len(first_digits)
        if total == 0:
            return {"error": "Empty data"}

        observed_counts = np.zeros(9)
        for d in first_digits:
            if 1 <= d <= 9:
                observed_counts[d-1] += 1
        
        observed_freq = observed_counts / total
        
        # Lei de Benford: P(d) = log10(1 + 1/d)
        expected_freq = np.log10(1 + 1/np.arange(1, 10))
        
        # Distância Euclidiana ou Chi-Square simplificado
        # Chi-Square: sum((Obs - Exp)^2 / Exp)
        # Mas aqui usaremos o M.A.D. (Mean Absolute Deviation) ou Divergência KL
        # Vamos usar um score simples de conformidade (0.0 a 1.0)
        
        # Divergência total absoluta
        abs_diff = np.sum(np.abs(observed_freq - expected_freq))
        
        # Threshold empírico: Se abs_diff < 0.05 (Muito Bom), < 0.15 (Aceitável), > 0.15 (Suspeito)
        status = "Normal"
        if abs_diff > 0.15:
            status = "Anômalo (Possível dupla compressão)"
        elif abs_diff > 0.10:
            status = "Desvio Moderado"
            
        return {
            "observed_freq": observed_freq.tolist(),
            "expected_freq": expected_freq.tolist(),
            "divergence_score": float(abs_diff),
            "status": status
        }

    def _analyze_fourier(self, sizes: List[int]) -> Dict[str, Any]:
        """Aplica FFT para identificar periodicidade dominante (Tamanho do GOP)."""
        # Se double compressed com GOPs diferentes, pode haver picos estranhos.
        # Normalment, o pico principal é 1/GOP_Size.
        
        N = len(sizes)
        if N < 30: # Muito curto para Fourier
            return {"status": "Amostra insuficiente"}

        # Remover média (DC component)
        data = np.array(sizes)
        data = data - np.mean(data)
        
        # FFT
        yf = fft(data)
        xf = np.linspace(0.0, 1.0/2.0, N//2) # Frequências (Cycles/Frame)
        amplitude = 2.0/N * np.abs(yf[0:N//2])
        
        # Encontrar picos (Simples)
        # Ignorar frequências muito baixas (perto de 0)
        min_idx = 5 
        if min_idx >= len(amplitude):
            return {"status": "Sem picos claros"}

        peak_idx = np.argmax(amplitude[min_idx:]) + min_idx
        peak_freq = xf[peak_idx]
        
        if peak_freq > 0:
            estimated_period = 1 / peak_freq # Em frames
        else:
            estimated_period = 0
            
        # Analisar "ruído" espectral (pode indicar double quantization)
        # Se houver muitos picos fortes concorrentes, é suspeito.
        noise_level = np.mean(amplitude)
        peak_ratio = amplitude[peak_idx] / noise_level if noise_level > 0 else 0
        
        return {
            "dominant_period_frames": float(estimated_period),
            "peak_strength": float(peak_ratio),
            "status": "Padrão GOP Forte" if peak_ratio > 3 else "Padrão GOP Fraco/Irregular"
        }

    def _generate_conclusion(self, benford, fourier) -> str:
        conclusions = []
        
        if "Anômalo" in benford.get("status", ""):
            conclusions.append("A distribuição dos tamanhos de frames viola estatisticamente a Lei de Benford, o que é comum em vídeos reprocessados ou gerados artificialmente.")
        elif "Normal" in benford.get("status", ""):
            conclusions.append("A distribuição estatística dos frames é natural e consistente.")
            
        if fourier.get("peak_strength", 0) > 5:
            conclusions.append(f"Detectada estrutura de GOP muito rígida (Período ~{fourier['dominant_period_frames']:.1f} frames).")
        elif fourier.get("peak_strength", 0) < 2:
            conclusions.append("Estrutura de GOP irregular ou muito complexa.")
            
        return " ".join(conclusions)
