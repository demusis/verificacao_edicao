"""
Módulo de detecção de áudio sintético (deepfake de voz).

Este módulo implementa técnicas heurísticas para detectar áudio
gerado por síntese de voz (TTS, voice cloning).
"""
import logging
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from core.case_manager import CaseManager
from core.config_schema import AnalysisConfig
from modules.base_module import BaseAnalysisModule

_logger = logging.getLogger(__name__)


class AudioDeepfakeModule(BaseAnalysisModule):
    """Módulo de detecção de áudio sintético/deepfake.
    
    Implementa análises heurísticas:
    - Mel-Spectrogram patterns
    - Formant consistency
    - Pitch stability
    - Micro-pause analysis
    """
    
    MODULE_NAME = "AudioDeepfake"
    
    def run(
        self,
        input_file: Path,
        output_filename: str = "audio_deepfake.json",
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> dict[str, Any]:
        """Executa detecção de áudio sintético.
        
        Args:
            input_file: Caminho do arquivo de áudio.
            output_filename: Nome do arquivo de saída JSON.
            progress_callback: Callback para reportar progresso.
            
        Returns:
            Dicionário com resultados da análise.
        """
        self._log_start(input_file)
        
        results: dict[str, Any] = {
            "filename": input_file.name,
            "status": "success",
            "analyses": {},
            "overall_score": 0.0,
            "verdict": "unknown"
        }
        
        fname = input_file.name
        
        try:
            # Carregar áudio
            self._notify_progress(f"[{fname}] Carregando áudio (deepfake)...", progress_callback)
            audio, sr = self._load_audio(input_file)
            
            if audio is None:
                results["status"] = "error"
                results["error"] = "Falha ao carregar áudio"
                self._save_results(results, output_filename)
                return results
            
            # 1. Análise de Mel-Spectrogram
            self._notify_progress(f"[{fname}] Analisando mel-spectrogram...", progress_callback)
            results["analyses"]["mel_patterns"] = self._analyze_mel_patterns(audio, sr)
            
            # 2. Análise de Formantes
            self._notify_progress(f"[{fname}] Analisando consistência de formantes...", progress_callback)
            results["analyses"]["formants"] = self._analyze_formants(audio, sr)
            
            # 3. Análise de Pitch
            self._notify_progress(f"[{fname}] Analisando estabilidade de pitch...", progress_callback)
            results["analyses"]["pitch"] = self._analyze_pitch_stability(audio, sr)
            
            # 4. Análise de Micro-pausas
            self._notify_progress(f"[{fname}] Analisando padrões de respiração/pausas...", progress_callback)
            results["analyses"]["pauses"] = self._analyze_micro_pauses(audio, sr)
            
            # Calcular score geral
            scores = [
                results["analyses"]["mel_patterns"].get("anomaly_score", 0),
                results["analyses"]["formants"].get("anomaly_score", 0),
                results["analyses"]["pitch"].get("anomaly_score", 0),
                results["analyses"]["pauses"].get("anomaly_score", 0),
            ]
            results["overall_score"] = float(np.mean(scores))
            
            # Veredicto
            if results["overall_score"] > 0.7:
                results["verdict"] = "highly_suspicious"
                results["verdict_text"] = "Alta probabilidade de áudio sintético/deepfake"
            elif results["overall_score"] > 0.4:
                results["verdict"] = "suspicious"
                results["verdict_text"] = "Características suspeitas detectadas - verificar manualmente"
            else:
                results["verdict"] = "likely_authentic"
                results["verdict_text"] = "Baixa probabilidade de síntese - parece autêntico"
            
        except Exception as e:
            self._log_error(e)
            results["status"] = "error"
            results["error"] = str(e)
        
        self._save_results(results, output_filename)
        return results
    
    def _load_audio(self, input_file: Path) -> tuple[Optional[np.ndarray], int]:
        """Carrega arquivo de áudio usando librosa com amostragem configurável.
        
        Estratégia:
        1. Início: X segundos (config.audio_segment_duration)
        2. Fim: X segundos
        3. Meio: N trechos aleatórios de X segundos (config.audio_random_segments)
        """
        try:
            import librosa
            import random
            
            # Obter duração total
            duration = librosa.get_duration(path=str(input_file))
            
            # Parâmetros da configuração
            if isinstance(self.config, dict):
                SEG_DUR = self.config.get('audio_segment_duration', 20.0)
                NUM_RND = self.config.get('audio_random_segments', 3)
            else:
                SEG_DUR = getattr(self.config, 'audio_segment_duration', 20.0)
                NUM_RND = getattr(self.config, 'audio_random_segments', 3)
            
            # Se o arquivo for curto (menor que 3x segmento), carregar tudo
            # Isso garante que não vamos tentar extrair mais do que existe
            if duration <= (SEG_DUR * 3):
                audio, sr = librosa.load(str(input_file), sr=None, mono=True)
                return audio, sr
            
            segments = []
            sr = None
            
            # 1. Segmento INICIAL
            seg, sr = librosa.load(str(input_file), sr=None, mono=True, 
                                   offset=0, duration=SEG_DUR)
            segments.append(seg)
            
            # 2. Segmentos ALEATÓRIOS (Meio)
            if NUM_RND > 0:
                # Intervalo válido para início dos segmentos aleatórios
                # Entre o fim do primeiro segmento e o início do último
                valid_start = SEG_DUR
                valid_end = duration - SEG_DUR - SEG_DUR
                
                if valid_end > valid_start:
                    # Gerar N pontos de início aleatórios
                    start_points = sorted([random.uniform(valid_start, valid_end) for _ in range(NUM_RND)])
                    
                    for start in start_points:
                        seg, _ = librosa.load(str(input_file), sr=sr, mono=True,
                                              offset=start, duration=SEG_DUR)
                        segments.append(seg)
            
            # 3. Segmento FINAL
            end_offset = max(0, duration - SEG_DUR)
            seg, _ = librosa.load(str(input_file), sr=sr, mono=True,
                                  offset=end_offset, duration=SEG_DUR)
            segments.append(seg)
            
            # Concatenar tudo
            audio = np.concatenate(segments)
            return audio, sr
            
        except Exception as e:
            _logger.error("Falha ao carregar áudio: %s", e)
            return None, 0
    
    def _analyze_mel_patterns(self, audio: np.ndarray, sr: int) -> dict[str, Any]:
        """Analisa padrões no mel-spectrogram para detectar síntese."""
        import librosa
        
        # Calcular mel-spectrogram
        mel_spec = librosa.feature.melspectrogram(y=audio, sr=sr, n_mels=128)
        mel_db = librosa.power_to_db(mel_spec, ref=np.max)
        
        # Detectar padrões geométricos regulares (indicativo de síntese)
        
        # 1. Variância por banda de mel (síntese tende a ser mais uniforme)
        band_variances = np.var(mel_db, axis=1)
        mean_band_variance = float(np.mean(band_variances))
        
        # 2. Autocorrelação temporal (síntese pode ter padrões repetitivos)
        temporal_mean = np.mean(mel_db, axis=0)
        autocorr = np.correlate(temporal_mean, temporal_mean, mode='full')
        autocorr = autocorr[len(autocorr)//2:]  # Apenas lag positivo
        if autocorr[0] != 0:
            autocorr = autocorr / autocorr[0]  # Normalizar
        
        # Picos de autocorrelação indicam periodicidade artificial
        from scipy.signal import find_peaks
        peaks, _ = find_peaks(autocorr[10:], height=0.3, distance=10)
        periodic_peaks = len(peaks)
        
        # 3. Suavidade excessiva das transições
        temporal_diff = np.diff(mel_db, axis=1)
        transition_roughness = float(np.mean(np.abs(temporal_diff)))
        
        # Score de anomalia
        anomaly_score = 0.0
        notes = []
        
        if mean_band_variance < 50:
            anomaly_score += 0.3
            notes.append("Variância espectral baixa (uniformidade suspeita)")
        
        if periodic_peaks > 5:
            anomaly_score += 0.4
            notes.append(f"{periodic_peaks} padrões periódicos detectados")
        
        if transition_roughness < 2.0:
            anomaly_score += 0.3
            notes.append("Transições muito suaves (possível síntese)")
        
        return {
            "mean_band_variance": mean_band_variance,
            "periodic_peaks_count": periodic_peaks,
            "transition_roughness": transition_roughness,
            "anomaly_score": min(anomaly_score, 1.0),
            "forensic_note": "; ".join(notes) if notes else "Padrões de mel-spectrogram normais",
        }
    
    def _analyze_formants(self, audio: np.ndarray, sr: int) -> dict[str, Any]:
        """Analisa consistência de formantes vocais."""
        import librosa
        
        # Usar LPC para estimar formantes (simplificado)
        # Dividir em frames
        frame_length = int(0.025 * sr)  # 25ms
        hop_length = int(0.010 * sr)  # 10ms
        
        # Centroid como proxy para formantes
        spectral_centroid = librosa.feature.spectral_centroid(
            y=audio, sr=sr, n_fft=frame_length, hop_length=hop_length
        )[0]
        
        # MFCC para capturar características vocais
        mfccs = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=13)
        
        # Estatísticas dos MFCCs
        mfcc_means = np.mean(mfccs, axis=1)
        mfcc_stds = np.std(mfccs, axis=1)
        
        # Coeficiente de variação do centroid
        centroid_cv = float(np.std(spectral_centroid) / (np.mean(spectral_centroid) + 1e-10))
        
        # Delta MFCCs (variação temporal)
        mfcc_delta = librosa.feature.delta(mfccs)
        delta_energy = float(np.mean(np.abs(mfcc_delta)))
        
        # Detectar estabilidade artificial
        anomaly_score = 0.0
        notes = []
        
        # Coeficiente de variação muito baixo indica síntese
        if centroid_cv < 0.15:
            anomaly_score += 0.4
            notes.append("Centroid espectral excessivamente estável")
        
        # Pouca variação nos MFCCs
        if np.mean(mfcc_stds[1:]) < 5:  # Ignorar MFCC[0] (energia)
            anomaly_score += 0.3
            notes.append("MFCCs com baixa variação (formantes estáveis demais)")
        
        # Delta baixo indica falta de naturalidade
        if delta_energy < 0.5:
            anomaly_score += 0.3
            notes.append("Baixa dinâmica temporal nos coeficientes vocais")
        
        return {
            "centroid_cv": centroid_cv,
            "mfcc_mean_std": float(np.mean(mfcc_stds[1:])),
            "delta_energy": delta_energy,
            "anomaly_score": min(anomaly_score, 1.0),
            "forensic_note": "; ".join(notes) if notes else "Características de formantes normais",
        }
    
    def _analyze_pitch_stability(self, audio: np.ndarray, sr: int) -> dict[str, Any]:
        """Analisa estabilidade do pitch (tom de voz)."""
        import librosa
        
        # Extrair pitch usando pyin
        try:
            f0, voiced_flag, voiced_probs = librosa.pyin(
                audio, fmin=50, fmax=500, sr=sr
            )
        except Exception:
            # Fallback se pyin falhar
            return {
                "error": "Falha na extração de pitch",
                "anomaly_score": 0.0,
                "forensic_note": "Não foi possível analisar pitch",
            }
        
        # Filtrar apenas frames com voz
        valid_f0 = f0[~np.isnan(f0)]
        
        if len(valid_f0) < 10:
            return {
                "voiced_frames": len(valid_f0),
                "anomaly_score": 0.0,
                "forensic_note": "Poucos frames com voz detectados",
            }
        
        # Estatísticas de pitch
        pitch_mean = float(np.mean(valid_f0))
        pitch_std = float(np.std(valid_f0))
        pitch_range = float(np.max(valid_f0) - np.min(valid_f0))
        
        # Coeficiente de variação
        pitch_cv = pitch_std / (pitch_mean + 1e-10)
        
        # Jitter (variação frame-a-frame)
        jitter = np.mean(np.abs(np.diff(valid_f0))) / (pitch_mean + 1e-10)
        
        # Score de anomalia
        anomaly_score = 0.0
        notes = []
        
        # Pitch muito estável é suspeito
        if pitch_cv < 0.05:
            anomaly_score += 0.5
            notes.append("Pitch excessivamente estável (não natural)")
        
        # Range muito limitado
        if pitch_range < 20:
            anomaly_score += 0.3
            notes.append(f"Range de pitch muito limitado ({pitch_range:.1f} Hz)")
        
        # Jitter muito baixo (TTS moderno é muito suave)
        if jitter < 0.01:
            anomaly_score += 0.2
            notes.append("Transições de pitch muito suaves")
        
        return {
            "pitch_mean_hz": pitch_mean,
            "pitch_std_hz": pitch_std,
            "pitch_range_hz": pitch_range,
            "pitch_cv": float(pitch_cv),
            "jitter": float(jitter),
            "voiced_frames": len(valid_f0),
            "anomaly_score": min(anomaly_score, 1.0),
            "forensic_note": "; ".join(notes) if notes else "Características de pitch normais",
        }
    
    def _analyze_micro_pauses(self, audio: np.ndarray, sr: int) -> dict[str, Any]:
        """Analisa padrões de micro-pausas e respiração."""
        import librosa
        
        # Calcular RMS para detectar pausas
        frame_length = int(0.025 * sr)
        hop_length = int(0.010 * sr)
        rms = librosa.feature.rms(y=audio, frame_length=frame_length, hop_length=hop_length)[0]
        rms_db = librosa.amplitude_to_db(rms + 1e-10)
        
        # Threshold adaptativo para silêncio
        silence_threshold = np.percentile(rms_db, 10) + 10
        
        # Encontrar pausas
        is_pause = rms_db < silence_threshold
        
        # Calcular durações das pausas
        pause_durations = []
        speech_durations = []
        in_pause = False
        count = 0
        
        for is_p in is_pause:
            if is_p == in_pause:
                count += 1
            else:
                duration_ms = (count * hop_length / sr) * 1000
                if in_pause:
                    pause_durations.append(duration_ms)
                else:
                    speech_durations.append(duration_ms)
                in_pause = is_p
                count = 1
        
        # Última segmento
        duration_ms = (count * hop_length / sr) * 1000
        if in_pause:
            pause_durations.append(duration_ms)
        else:
            speech_durations.append(duration_ms)
        
        # Estatísticas
        pause_durations = np.array(pause_durations) if pause_durations else np.array([0])
        speech_durations = np.array(speech_durations) if speech_durations else np.array([0])
        
        mean_pause = float(np.mean(pause_durations))
        std_pause = float(np.std(pause_durations))
        pause_cv = std_pause / (mean_pause + 1e-10)
        
        # Micro-pausas (50-200ms) - respiração natural
        micro_pauses = np.sum((pause_durations > 50) & (pause_durations < 200))
        
        # Score de anomalia
        anomaly_score = 0.0
        notes = []
        
        # TTS geralmente tem pausas muito regulares
        if len(pause_durations) > 5 and pause_cv < 0.3:
            anomaly_score += 0.4
            notes.append("Pausas excessivamente regulares")
        
        # Falta de micro-pausas (respiração)
        if len(pause_durations) > 10 and micro_pauses < 2:
            anomaly_score += 0.3
            notes.append("Ausência de pausas de respiração naturais")
        
        # Segmentos de fala muito uniformes
        if len(speech_durations) > 5:
            speech_cv = np.std(speech_durations) / (np.mean(speech_durations) + 1e-10)
            if speech_cv < 0.2:
                anomaly_score += 0.3
                notes.append("Segmentos de fala com duração muito regular")
        
        return {
            "pause_count": len(pause_durations),
            "mean_pause_ms": mean_pause,
            "pause_cv": float(pause_cv),
            "micro_pause_count": int(micro_pauses),
            "anomaly_score": min(anomaly_score, 1.0),
            "forensic_note": "; ".join(notes) if notes else "Padrões de pausas naturais",
        }
