import cv2
import numpy as np
import os
import sys
from pathlib import Path
from skimage.feature import local_binary_pattern

def get_haarcascades_path():
    """Retorna o caminho para os arquivos haarcascades, compatível com PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        # Executando dentro de um executável PyInstaller
        # Os arquivos XML são copiados diretamente para cv2/data/
        return os.path.join(sys._MEIPASS, 'cv2', 'data') + os.sep
    else:
        # Executando normalmente (desenvolvimento)
        return cv2.data.haarcascades

class DeepfakeAnalysisModule:
    """
    Módulo de análise forense para detecção de Deepfakes e Splicing.
    Implementa verificações de:
    1. Consistência Física (Ruído/ELA) entre Sujeito e Fundo.
    2. Artefatos de Frequência (FFT) típicos de GANs.
    3. Análise de Textura (LBP) com histograma para detecção de suavização.
    4. Análise Global para imagens sem faces/corpos detectados.
    """

    def __init__(self, config=None):
        # Converter objeto AnalysisConfig para dict se necessário
        if config is not None:
            if hasattr(config, 'to_dict'):
                self.config = config.to_dict()
            else:
                self.config = config
        else:
            self.config = {}
        # Carregar Classificadores - compatível com PyInstaller
        haarcascades_path = get_haarcascades_path()
        self.face_cascade = cv2.CascadeClassifier(haarcascades_path + 'haarcascade_frontalface_default.xml')
        self.eye_cascade = cv2.CascadeClassifier(haarcascades_path + 'haarcascade_eye.xml')
        
        # Detector de Pessoas (HOG)
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def run(self, image_path: str):
        """Wrapper de compatibilidade para imagens."""
        return self.run_image(image_path)

    def run_image(self, image_path: str):
        """Executa análise em uma única imagem."""
        result = self._init_result()
        try:
            # Leitura robusta
            file_bytes = np.fromfile(str(image_path), np.uint8)
            img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

            if img is None:
                raise ValueError("Erro ao carregar imagem.")
            
            frame_res = self._analyze_frame(img)
            result.update(frame_res)
            
            # Decisão Final para Imagem
            self._finalize_result(result)

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            
        return result

    def run_video(self, video_path: str, sample_rate=30):
        """Executa análise em vídeo (Frame-by-Frame + Temporal)."""
        result = self._init_result()
        result["type"] = "video"
        result["temporal_jitter"] = 0
        
        try:
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                raise ValueError("Erro ao abrir vídeo.")
            
            frame_count = 0
            analyzed_frames = 0
            
            # Histórico para análise temporal
            history_consistency = []
            history_fft = []
            history_texture = []
            
            while True:
                ret, frame = cap.read()
                if not ret: break
                
                frame_count += 1
                if frame_count % sample_rate != 0: continue
                
                # Analisar Frame
                f_res = self._analyze_frame(frame)
                analyzed_frames += 1
                
                # Acumular máximos (Pior caso)
                result["detected_faces"] = max(result["detected_faces"], f_res["detected_faces"])
                result["detected_bodies"] = max(result["detected_bodies"], f_res["detected_bodies"])
                
                # Guardar histórico para Jitter
                history_consistency.append(f_res["consistency_score"])
                history_fft.append(f_res["frequency_score"])
                history_texture.append(f_res["texture_score"])
                
                # Se encontrar algo muito grave em um frame, reportar
                if f_res["is_suspicious"]:
                    if len(result["details"]) < 5: # Limitar logs
                        result["details"].append(f"Frame {frame_count}: " + "; ".join(f_res["details"]))

            cap.release()
            
            if analyzed_frames == 0:
                result["status"] = "skipped"
                return result

            # Calcular Médias e Jitter (Desvio Padrão Temporal)
            result["consistency_score"] = int(np.mean(history_consistency))
            result["frequency_score"] = int(np.mean(history_fft))
            result["texture_score"] = int(np.mean(history_texture))
            
            jitter_cons = np.std(history_consistency)
            jitter_fft = np.std(history_fft)
            jitter_tex = np.std(history_texture)
            
            result["temporal_jitter"] = int((jitter_cons + jitter_fft + jitter_tex) / 3)
            
            # Se algum frame foi suspeito, o vídeo é suspeito
            for frame_cons in history_consistency:
                if frame_cons > 70: result["is_suspicious"] = True
            for frame_fft in history_fft:
                if frame_fft > 70: result["is_suspicious"] = True
            for frame_tex in history_texture:
                if frame_tex > 70: result["is_suspicious"] = True
            
            jitter_threshold = int(self.config.get('deepfake_jitter_threshold', 15))
            if result["temporal_jitter"] > jitter_threshold:
                result["is_suspicious"] = True
                result["details"].append(f"Alta Instabilidade Temporal (Jitter: {result['temporal_jitter']}). Provável Deepfake instável.")

            self._finalize_result(result)

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            
        return result

    def _init_result(self):
        return {
            "status": "success",
            "type": "image",
            "detected_faces": 0,
            "detected_bodies": 0,
            "consistency_score": 0,
            "frequency_score": 0,
            "texture_score": 0,
            "noise_score": 0,
            "eye_consistency": "N/A",
            "is_suspicious": False,
            "analysis_type": "face_body",
            "details": []
        }

    def _finalize_result(self, result):
        # Heurística final baseada nas métricas acumuladas
        # Exigir MÚLTIPLOS indicadores para reduzir falsos positivos
        suspicious_count = 0
        
        if result["frequency_score"] > 70:
            suspicious_count += 1
            if "Artefatos de alta frequência" not in str(result["details"]):
                result["details"].append("Artefatos de GAN frequentes detectados.")
                
        if result["texture_score"] > 70:
            suspicious_count += 1
            if "Textura facial anormalmente lisa" not in str(result["details"]):
                result["details"].append("Textura artificial detectada.")

        if result["consistency_score"] > 70:
            suspicious_count += 1
            if "Inconsistência física" not in str(result["details"]):
                result["details"].append("Inconsistência de ruído/iluminação entre sujeito e fundo.")

        # Só marcar como suspeito se MÚLTIPLOS indicadores concordarem
        if suspicious_count >= 2:
            result["is_suspicious"] = True

    def _analyze_frame(self, img):
        """Analisa um único frame (numpy array)."""
        res = {
            "detected_faces": 0,
            "detected_bodies": 0,
            "consistency_score": 0,
            "frequency_score": 0,
            "texture_score": 0,
            "noise_score": 0,
            "is_suspicious": False,
            "analysis_type": "face_body",
            "details": []
        }
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        ycbcr = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
        
        # 1. Detecção
        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
        bodies, _ = self.hog.detectMultiScale(img, winStride=(8,8), padding=(32,32), scale=1.05)
        
        res["detected_faces"] = len(faces)
        res["detected_bodies"] = len(bodies)
        
        # Se não detectar faces nem corpos, fazer análise global da imagem
        if len(faces) == 0 and len(bodies) == 0:
            global_res = self._analyze_global_image(img, gray)
            res.update(global_res)
            return res

        # 2. Máscaras
        mask_subject = np.zeros_like(gray)
        for (x,y,w,h) in faces: cv2.rectangle(mask_subject, (x,y), (x+w,y+h), 255, -1)
        for (x,y,w,h) in bodies: cv2.rectangle(mask_subject, (x,y), (x+w,y+h), 255, -1)
        mask_background = cv2.bitwise_not(mask_subject)
        
        # 3. Consistência de Ruído (Proxy de Splicing)
        noise_map = cv2.Laplacian(gray, cv2.CV_64F)
        noise_var_subject = np.var(noise_map[mask_subject > 0]) if np.any(mask_subject > 0) else 0
        noise_var_bg = np.var(noise_map[mask_background > 0]) if np.any(mask_background > 0) else 0
        
        max_var = max(noise_var_subject, noise_var_bg, 1e-5)
        diff_ratio = abs(noise_var_subject - noise_var_bg) / max_var
        
        res["consistency_score"] = int(diff_ratio * 100)

        if diff_ratio > (int(self.config.get('deepfake_noise_threshold', 50)) / 100.0):
            res["details"].append(f"Inconsistência de Ruído Sujeito/Fundo ({diff_ratio:.2f})")
            if diff_ratio > 0.7: res["is_suspicious"] = True

        # 4. FFT e Textura (Faces) - Foco em AI/Deepfake
        max_fft = 0
        max_tex = 0
        
        for (x,y,w,h) in faces:
            # ROI da face em escala de cinza e YCbCr
            face_roi_gray = gray[y:y+h, x:x+w]
            face_roi_ycbcr = ycbcr[y:y+h, x:x+w]
            
            if face_roi_gray.size < 400:  # ROI mínimo para análise confiável
                continue
                
            # FFT nos canais de luminância e crominância
            fft_y = self._analyze_frequency_artifacts(face_roi_ycbcr[:,:,0]) # Y
            fft_cr = self._analyze_frequency_artifacts(face_roi_ycbcr[:,:,1]) # Cr
            fft_cb = self._analyze_frequency_artifacts(face_roi_ycbcr[:,:,2]) # Cb
            
            # Textura na face
            tex = self._analyze_texture_lbp(face_roi_gray)
            
            # Score de frequência é o maior entre os canais (IA costuma falhar na crominância)
            current_fft = max(fft_y, int(fft_cr * 1.2), int(fft_cb * 1.2))
            max_fft = max(max_fft, current_fft)
            max_tex = max(max_tex, tex)
            
        res["frequency_score"] = min(100, max_fft)
        res["texture_score"] = max_tex
        
        # Decisão baseada na combinação (Moderna Diffusion Detection)
        if res["frequency_score"] > 70:
            res["details"].append("Artefatos de frequência anômalos detectados (provável GAN/Diffusion).")
        if res["texture_score"] > 70:
            res["details"].append("Textura facial excessivamente regular ou suavizada (padrão AI).")

        if (res["frequency_score"] > 65 and res["texture_score"] > 65) or res["frequency_score"] > 85 or res["texture_score"] > 85:
            res["is_suspicious"] = True
        
        return res

    def _analyze_global_image(self, img, gray):
        """
        Análise de deepfake para imagens SEM faces/corpos detectados.
        """
        res = {
            "analysis_type": "global_image",
            "frequency_score": 0,
            "texture_score": 0,
            "noise_score": 0,
            "is_suspicious": False,
            "details": ["Nenhuma face/corpo detectado. Executando análise global."]
        }
        
        ycbcr = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
        
        # FFT nos canais Cr e Cb costuma ser mais revelador em Diffusion global
        fft_cr = self._analyze_frequency_artifacts(ycbcr[:,:,1])
        fft_cb = self._analyze_frequency_artifacts(ycbcr[:,:,2])
        res["frequency_score"] = max(fft_cr, fft_cb)
        
        # LBP Global
        res["texture_score"] = self._analyze_texture_lbp(gray)
        
        # Inconsistência de Blocos
        res["noise_score"] = self._analyze_noise_blocks(gray)
        
        # Decisão para imagem global
        indicators = 0
        if res["frequency_score"] > 65: indicators += 1
        if res["texture_score"] > 65: indicators += 1
        if res["noise_score"] > 70: indicators += 1
        
        if indicators >= 2 or res["frequency_score"] > 80:
            res["is_suspicious"] = True
            
        return res

    def _analyze_noise_blocks(self, gray, block_size=64):
        """
        Analisa consistência de ruído dividindo imagem em blocos.
        """
        try:
            h, w = gray.shape
            variances = []
            
            for y in range(0, h - block_size, block_size):
                for x in range(0, w - block_size, block_size):
                    block = gray[y:y+block_size, x:x+block_size]
                    lap = cv2.Laplacian(block, cv2.CV_64F)
                    variances.append(np.var(lap))
            
            if len(variances) < 4: return 0
            
            mean_var = np.mean(variances)
            std_var = np.std(variances)
            if mean_var < 1e-5: return 0
            
            cv = std_var / mean_var
            return min(100, int(cv * 60)) # Ajustado peso
            
        except Exception:
            return 0

    def _analyze_frequency_artifacts(self, roi):
        """
        Detecta picos anômalos no espectro de frequência.
        Melhorado para ser mais sensível a padrões de interpolação e Diffusion.
        """
        try:
            if roi.shape[0] < 32 or roi.shape[1] < 32: return 0
                
            # Aplicar janela de Hanning para reduzir leakage espectral
            win_y = np.hanning(roi.shape[0])
            win_x = np.hanning(roi.shape[1])
            window = np.outer(win_y, win_x)
            roi_windowed = roi * window
            
            f = np.fft.fft2(roi_windowed)
            fshift = np.fft.fftshift(f)
            magnitude_spectrum = np.abs(fshift)
            
            # Log magnitude para análise
            log_mag = np.log(magnitude_spectrum + 1)
            
            # Analisar altas frequências (região externa do espectro)
            h, w = log_mag.shape
            cy, cx = h // 2, w // 2
            y, x = np.ogrid[:h, :w]
            dist_from_center = np.sqrt((x - cx)**2 + (y - cy)**2)
            
            mask_high = dist_from_center > (min(h, w) * 0.4)
            if not np.any(mask_high): return 0
            
            high_freq_values = log_mag[mask_high]
            
            # Procura por picos (outliers) na alta frequência
            # Imagens naturais têm decaimento suave. IA tem picos por repetitividade de kernels.
            mean_h = np.mean(high_freq_values)
            max_h = np.max(high_freq_values)
            std_h = np.std(high_freq_values)
            
            peak_intensity = (max_h - mean_h) / (std_h + 1e-6)
            
            # Score baseado no desvio do pico em relação à média da alta freq
            score = min(100, int(peak_intensity * 15))
            
            return score
        except Exception:
            return 0

    def _analyze_texture_lbp(self, roi):
        """
        Análise de textura usando LBP Multi-escala.
        Imagens AI tendem a ter padrões de textura local muito uniformes em certas áreas.
        """
        try:
            if roi.shape[0] < 32 or roi.shape[1] < 32: return 0
            
            scores = []
            # Diferentes escalas para capturar texturas variadas
            configs = [(8, 1), (16, 2), (24, 3)]
            
            for P, R in configs:
                lbp = local_binary_pattern(roi, P, R, method='uniform')
                n_bins = P + 2
                hist, _ = np.histogram(lbp.ravel(), bins=n_bins, range=(0, n_bins), density=True)
                
                # Entropia (Imagens reais > Sintéticas)
                hist_clean = hist + 1e-10
                entropy = -np.sum(hist_clean * np.log2(hist_clean))
                
                # Concentração no padrão "smooth" (bin 0 ou bin max dependendo do pattern)
                max_bin_ratio = np.max(hist)
                
                # Heurística de score parcial
                p_score = 0
                if entropy < (P * 0.15): p_score += 40 # Muito baixa entropia
                if max_bin_ratio > 0.3: p_score += 40 # Concentração excessiva
                scores.append(p_score)
                
            return min(100, int(np.mean(scores)))
            
        except Exception:
            return 0

    def _analyze_eyes(self, face_roi):
        """Verifica se há brilhos especulares idênticos ou falta de detalhe na íris."""
        # TODO: Implementar análise de brilho especular (refraction consistency)
        eyes = self.eye_cascade.detectMultiScale(face_roi)
        if len(eyes) < 2:
            return "Indeterminado (Obscurecido)"
        return "Normal"

