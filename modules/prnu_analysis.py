import json
from pathlib import Path

import cv2
import numpy as np
import pywt

from core.case_manager import CaseManager


class PrnuAnalysisModule:
    """
    Módulo para análise de PRNU (Photo-Response Non-Uniformity).
    Extrai o fingerprint da câmera (ruído do sensor) e compara entre vídeos.
    """
    def __init__(self, case_manager: CaseManager):
        self.cm = case_manager
        self.logger = self.cm.get_logger()
        self.frame_limit = 30 # MVP: Limit frames to speed up (Forensic std is 50+)

    def run(self, input_file: Path, output_filename: str = "prnu_analysis.json"):
        """Extrai o PRNU do vídeo e salva o fingerprint (.npy) e metadados (.json)."""
        self.logger.log("PRNU_START", {"file": input_file.name})
        
        try:
            # 1. Extração Frame a Frame
            fingerprint, frames_used = self._extract_fingerprint(input_file)

            # 2. Salvar Fingerprint (.npy) apenas se a extração funcionou
            npy_filename = output_filename.replace(".json", ".npy")
            if fingerprint is not None:
                npy_path = self.cm.results_dir / npy_filename
                np.save(npy_path, fingerprint)

            # 3. Salvar Metadados (.json)
            result = {
                "fingerprint_file": npy_filename if fingerprint is not None else None,
                "frames_used": frames_used,
                "resolution": fingerprint.shape if fingerprint is not None else "N/A",
                "status": "extracted" if fingerprint is not None else "failed"
            }
            
            out_path = self.cm.results_dir / output_filename
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=4)
                
            self.logger.log("PRNU_END", {"file": input_file.name, "status": "success"})
            return result
            
        except Exception as e:
            self.logger.log("PRNU_ERROR", {"error": str(e)})
            # Save error state
            out_path = self.cm.results_dir / output_filename
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump({"status": "error", "error": str(e)}, f)
            return {"status": "error"}

    def _extract_fingerprint(self, input_path: Path) -> tuple[np.ndarray | None, int]:
        """Lê frames/imagem, remove conteúdo (denoise) e extrai o resíduo de ruído.

        Returns:
            Tupla (fingerprint ou None, número de frames efetivamente usados).
        """
        # Tentar abrir como imagem primeiro
        # Usar imdecode para suportar paths com acento (Windows)
        try:
             data = np.fromfile(str(input_path), dtype=np.uint8)
             img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        except Exception:
             img = None

        if img is not None:
             # Processing single image
             gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
             fingerprint = self._get_noise_residual_wavelet(gray)
             return fingerprint.astype(np.float32), 1

        # Se não for imagem, tentar como vídeo
        cap = cv2.VideoCapture(str(input_path))
        noise_sum = None
        count = 0
        try:
            if not cap.isOpened():
                raise OSError(f"Cannot open file: {input_path}")

            # Leitura sequencial (MVP). Ideal seria aleatória ou keyframes.
            while count < self.frame_limit:
                ret, frame = cap.read()
                if not ret:
                    break

                # Converter para Grayscale (PRNU geralmente é feito em Y ou Grayscale)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                h, w = gray.shape

                # Inicializar acumulador se necessário
                if noise_sum is None:
                    noise_sum = np.zeros((h, w), dtype=np.float32)

                # Extrair Ruído (Wavelet Denoising)
                # W = I - Denoised(I)
                noise_residual = self._get_noise_residual_wavelet(gray)
                noise_sum += noise_residual
                count += 1
        finally:
            cap.release()

        if count == 0:
            return None, 0

        # Média
        fingerprint = noise_sum / count

        # Zero-mean (remove artifacts)
        # fingerprint -= np.mean(fingerprint) # Opcional, o filtro wavelet ja deve remover low-freq

        return fingerprint.astype(np.float32), count

    def _get_noise_residual_wavelet(self, img_gray):
        """Extrai ruído usando decomposição Wavelet (Filtro de Wiener aproximado ou threshold)."""
        # Conversão para float
        im = img_gray.astype(np.float32)
        
        # Decomposição Wavelet (db4, level 4)
        coeffs = pywt.wavedec2(im, 'db4', level=4)
        
        # O detalhamento exato do filtro Mihcak é complexo. 
        # MVP: Zerar coeficientes de aproximação (Low frequency content) para sobrar apenas alta frequência (Ruído + Bordas)
        # E aplicar soft thresholding nos detalhes.
        
        # Na verdade, para PRNU queremos o resíduo: Img - Denoised.
        # Denoising simples: Zerar detalhes pequenos (noise) e reconstruir -> Imagem Limpa.
        # Ruído = Img - Imagem Limpa.
        
        # Vamos usar uma abordagem mais direta do OpenCV que é rápida para MVP se o user não tiver GPU para Wavelet complexo.
        # Mas já que temos PyWavelets, vamos tentar:
        # VisuShrink ou BayesShrink seria ideal.
        
        # Abordagem Simplificada Forense:
        # Obter a imagem denoised via Wavelet (remover componentes de alta frequência que correspondem a ruído gaussiano).
        # Para isso, zeramos os coeficientes de detalhe ABAIXO de um limiar (Denoising clássico).
        
        coeffs_thresh = list(coeffs)
        # Coeffs[0] é Aproximação (LL). Mantém.
        # Coeffs[1..] são Detalhes (LH, HL, HH).
        
        sigma = 5.0 # Estimativa padrão de ruído de câmera
        
        # Thresholding manual simples
        for i in range(1, len(coeffs_thresh)):
            coeffs_thresh[i] = tuple(pywt.threshold(c, sigma, mode='soft') for c in coeffs_thresh[i])
            
        im_denoised = pywt.waverec2(coeffs_thresh, 'db4')
        
        # Crop para tamanho original (Wavelet pode mudar tamanho levemente se impar)
        h, w = img_gray.shape
        im_denoised = im_denoised[:h, :w]
        
        residual = im - im_denoised
        return residual

    @staticmethod
    def compare_fingerprints(fp1_path: Path, fp2_path: Path) -> dict:
        """Compara dois fingerprints (.npy) e retorna métricas (PCE, Correlation)."""
        try:
            k1 = np.load(fp1_path)
            k2 = np.load(fp2_path)
            
            # Validar tamanhos (Devem ser iguais ou crop na intersecção)
            # Validar tamanhos e Redimensionar (Normalização)
            h1, w1 = k1.shape
            h2, w2 = k2.shape
            
            scaling_note = None
            
            # Diferença de área > 5% indica resoluções diferentes (ex: 720p vs 1080p)
            area1, area2 = h1 * w1, h2 * w2
            
            if abs(area1 - area2) / max(area1, area2) > 0.05:
                # Redimensionar o menor para o tamanho do maior (Upscaling do ruído)
                if area1 < area2:
                    # k1 é menor -> Resize k1 para (w2, h2)
                    crop1 = cv2.resize(k1, (w2, h2), interpolation=cv2.INTER_CUBIC)
                    crop2 = k2
                    scaling_note = f"Resize (1->2): {w1}x{h1} para {w2}x{h2}"
                else:
                    # k2 é menor -> Resize k2 para (w1, h1)
                    crop1 = k1
                    crop2 = cv2.resize(k2, (w1, h1), interpolation=cv2.INTER_CUBIC)
                    scaling_note = f"Resize (2->1): {w2}x{h2} para {w1}x{h1}"
            else:
                # Tamanhos similares: Crop Central para garantir match exato de pixel
                min_h, min_w = min(h1, h2), min(w1, w2)
                cy1, cx1 = h1 // 2, w1 // 2
                cy2, cx2 = h2 // 2, w2 // 2
                
                crop1 = k1[cy1 - min_h//2 : cy1 + min_h//2, cx1 - min_w//2 : cx1 + min_w//2]
                crop2 = k2[cy2 - min_h//2 : cy2 + min_h//2, cx2 - min_w//2 : cx2 + min_w//2]
            
            # Cross Correlation Normalizada
            # PCE = Peak to Correlation Energy
            
            # Cálculo eficiente usando FFT para Correlação Cruzada 2D
            f1 = np.fft.fft2(crop1)
            f2 = np.fft.fft2(crop2)
            conj_f2 = np.conj(f2)
            
            # R = F-1(F1 * conj(F2))
            correlation = np.fft.ifft2(f1 * conj_f2)
            correlation = np.real(correlation)
            correlation = np.fft.fftshift(correlation) # Centralizar o pico
            
            # PCE Calculation
            # Pico máximo
            peak_y, peak_x = np.unravel_index(np.argmax(correlation), correlation.shape)
            peak_val = correlation[peak_y, peak_x]
            
            # Energia (excluindo uma vizinhança do pico)
            h, w = correlation.shape
            radius = 11 # Vizinhança padrão
            y_grid, x_grid = np.ogrid[-peak_y:h-peak_y, -peak_x:w-peak_x]
            mask = x_grid**2 + y_grid**2 > radius**2
            
            energy = np.mean(correlation[mask]**2) if mask.any() else 0.0

            pce = (peak_val**2) / energy if energy > 0 else 0
            
            return {
                "pce": float(pce),
                "peak": float(peak_val),
                "energy": float(energy),
                "match": bool(pce > 60.0), # Threshold padrão comum na literatura (varia de 45 a 60)
                "scaling_note": scaling_note
            }
        except Exception as e:
            return {"error": str(e), "pce": 0.0, "match": False, "scaling_note": None}
