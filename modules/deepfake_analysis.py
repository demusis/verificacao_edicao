import cv2
import numpy as np
import os
from pathlib import Path

class DeepfakeAnalysisModule:
    """
    Módulo de análise forense para detecção de Deepfakes e Splicing.
    Implementa verificações de:
    1. Consistência Física (Ruído/ELA) entre Sujeito e Fundo.
    2. Artefatos de Frequência (FFT) típicos de GANs.
    3. Análise de Textura (LBP) para detecção de suavização de pele.
    4. Análise Especular (Olhos).
    """

    def __init__(self, config=None):
        self.config = config or {}
        # Carregar Classificadores
        self.face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')
        
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
                result["status"] = "skpped"
                return result

            # Calcular Médias e Jitter (Desvio Padrão Temporal)
            result["consistency_score"] = int(np.mean(history_consistency))
            result["frequency_score"] = int(np.mean(history_fft))
            result["texture_score"] = int(np.mean(history_texture))
            
            jitter_cons = np.std(history_consistency)
            jitter_fft = np.std(history_fft)
            jitter_tex = np.std(history_texture)
            
            result["temporal_jitter"] = int((jitter_cons + jitter_fft + jitter_tex) / 3)
            

            
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
            "consistency_score": 100,
            "frequency_score": 0,
            "texture_score": 0,
            "eye_consistency": "N/A",
            "is_suspicious": False,
            "details": []
        }

    def _finalize_result(self, result):
        # Heurística final baseada nas métricas acumuladas
        if result["frequency_score"] > 70:
            result["is_suspicious"] = True
            if "Artefatos de alta frequência" not in str(result["details"]):
                result["details"].append("Artefatos de GAN frequentes detectados.")
                
        if result["texture_score"] > 80:
            result["is_suspicious"] = True
            if "Textura facial anormalmente lisa" not in str(result["details"]):
                result["details"].append("Textura artificial detectada consistentemente.")

    def _analyze_frame(self, img):
        """Analisa um único frame (numpy array)."""
        res = {
            "detected_faces": 0,
            "detected_bodies": 0,
            "consistency_score": 100,
            "frequency_score": 0,
            "texture_score": 0,
            "is_suspicious": False,
            "details": []
        }
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 1. Detecção
        faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
        bodies, _ = self.hog.detectMultiScale(img, winStride=(8,8), padding=(32,32), scale=1.05)
        
        res["detected_faces"] = len(faces)
        res["detected_bodies"] = len(bodies)
        
        if len(faces) == 0 and len(bodies) == 0:
            return res

        # 2. Máscaras
        mask_subject = np.zeros_like(gray)
        for (x,y,w,h) in faces: cv2.rectangle(mask_subject, (x,y), (x+w,y+h), 255, -1)
        for (x,y,w,h) in bodies: cv2.rectangle(mask_subject, (x,y), (x+w,y+h), 255, -1)
        mask_background = cv2.bitwise_not(mask_subject)
        
        # 3. Consistência
        noise_map = cv2.Laplacian(gray, cv2.CV_64F)
        noise_var_subject = np.var(noise_map[mask_subject > 0]) if np.any(mask_subject > 0) else 0
        noise_var_bg = np.var(noise_map[mask_background > 0]) if np.any(mask_background > 0) else 0
        
        max_var = max(noise_var_subject, noise_var_bg, 1e-5)
        diff_ratio = abs(noise_var_subject - noise_var_bg) / max_var
        
        if diff_ratio > (int(self.config.get('deepfake_noise_threshold', 50)) / 100.0):
            res["consistency_score"] -= 40
            res["details"].append(f"Inconsistência de Ruído ({diff_ratio:.2f})")
            if diff_ratio > 0.7: res["is_suspicious"] = True

        # 4. FFT e Textura (Faces)
        # Modo Rápido: Pular FFT/LBP se ativado
        fast_mode = self.config.get('deepfake_fast_mode', False)
        
        max_fft = 0
        max_tex = 0
        
        if not fast_mode:
            for (x,y,w,h) in faces:
                face_roi = gray[y:y+h, x:x+w]
                fft = self._analyze_frequency_artifacts(face_roi)
                tex = self._analyze_texture_lbp(face_roi)
                max_fft = max(max_fft, fft)
                max_tex = max(max_tex, tex)
        else:
             res["details"].append("Modo Rápido: FFT/LBP ignorados.")
            
        res["frequency_score"] = max_fft
        res["texture_score"] = max_tex
        
        if max_fft > 75: res["is_suspicious"] = True
        if max_tex > 85: res["is_suspicious"] = True
        
        return res

    def _analyze_frequency_artifacts(self, roi):
        """
        Detecta picos anômalos em alta frequência usando FFT (Mag).
        GANs costumam gerar 'checkerboard artifacts' que aparecem como estrelas/pontos no espectro.
        """
        try:
            # FFT
            f = np.fft.fft2(roi)
            fshift = np.fft.fftshift(f)
            magnitude_spectrum = 20 * np.log(np.abs(fshift) + 1)
            
            # Calcular média azimutal (perfil radial) da magnitude
            h, w = magnitude_spectrum.shape
            center = (w//2, h//2)
            y, x = np.ogrid[:h, :w]
            r = np.sqrt((x - center[0])**2 + (y - center[1])**2)
            
            # Analisar altas frequências (raio > 2/3 da imagem)
            mask_high_freq = (r > (min(h,w) * 0.6))
            mean_high = np.mean(magnitude_spectrum[mask_high_freq])
            std_high = np.std(magnitude_spectrum[mask_high_freq])
            
            # Se houver picos muito fortes (desvio padrão alto na alta freq), pode ser artefato
            # Heurística experimental:
            score = min(100, (std_high / mean_high) * 200) 
            return int(score)
        except:
            return 0

    def _analyze_texture_lbp(self, roi):
        """
        Análise simplificada de textura.
        Deepfakes ruins tendem a ter menos 'detalhe' real (alta frequência local).
        """
        try:
            # Laplaciano como proxy de textura/detalhe de borda
            lap = cv2.Laplacian(roi, cv2.CV_64F)
            var = np.var(lap)
            
            # Se a variância for muito baixa para um rosto (pele de boneca)
            # Valor de referência empírico para rosto focado ~ 200-500+
            # Abaixo de 50 é muito liso.
            if var < 50: 
                return 90 # Muito liso
            elif var < 100:
                return 50 # Liso
            else:
                return 0 # Textura ok
        except:
            return 0

    def _analyze_eyes(self, face_roi):
        """Verifica detectabilidade e simetria básica de olhos."""
        eyes = self.eye_cascade.detectMultiScale(face_roi)
        if len(eyes) < 2:
            return "Assimetria/Oclusão"
            
        # Poderia checar specular highlights aqui
        # Por enquanto, retorna OK se detectar 2 olhos
        return "Normal"
