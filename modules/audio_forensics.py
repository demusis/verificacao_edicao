"""
Módulo de análise forense de áudio.

Este módulo implementa técnicas de análise forense para arquivos de áudio,
incluindo extração de metadados, análise espectral, consistência de ruído,
detecção de descontinuidade de fase e silêncio anômalo.
"""
import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from core.case_manager import CaseManager
from core.config_schema import AnalysisConfig
from core.hashing import calculate_file_hash, calculate_stream_hash
from modules.base_module import BaseAnalysisModule

_logger = logging.getLogger(__name__)


class AudioForensicsModule(BaseAnalysisModule):
    """Módulo de análise forense de áudio.
    
    Implementa análises de:
    - Metadados (codec, bitrate, sample rate, tags)
    - Estatísticas espectrais (FFT)
    - Consistência de ruído (noise floor)
    - Detecção de descontinuidade de fase
    - Detecção de silêncio anômalo
    """
    
    MODULE_NAME = "AudioForensics"
    
    SUPPORTED_EXTENSIONS = {'.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma', '.opus'}
    
    def run(
        self,
        input_file: Path,
        output_filename: str = "audio_analysis.json",
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> dict[str, Any]:
        """Executa análise forense completa no arquivo de áudio.
        
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
            "analyses": {}
        }
        
        fname = input_file.name
        
        try:
            # 1. Integridade (Hash)
            self._notify_progress(f"[{fname}] Calculando Hash SHA-512...", progress_callback)
            results["file_hash"] = calculate_file_hash(input_file)
            results["stream_hash"] = calculate_stream_hash(input_file, stream_type='a')

            # 2. Extrair metadados via FFprobe
            self._notify_progress(f"[{fname}] Extraindo metadados de áudio...", progress_callback)
            results["analyses"]["metadata"] = self._extract_metadata(input_file)
            
            # 2. Carregar áudio para análise
            self._notify_progress(f"[{fname}] Carregando áudio...", progress_callback)
            audio_data, sample_rate, error_msg = self._load_audio(input_file)
            
            if audio_data is None:
                results["status"] = "error"
                results["error"] = f"Falha ao carregar áudio: {error_msg}"
                self._save_results(results, output_filename)
                return results
            
            # 3. Análise espectral (apenas estatísticas)
            self._notify_progress(f"[{fname}] Análise espectral...", progress_callback)
            results["analyses"]["spectral"] = self._analyze_spectral(audio_data, sample_rate)
            
            # 4. Consistência de ruído (apenas estatísticas)
            self._notify_progress(f"[{fname}] Análise de ruído de fundo...", progress_callback)
            results["analyses"]["noise"] = self._analyze_noise_consistency(audio_data, sample_rate)
            
            # 5. Detecção de descontinuidade de fase
            self._notify_progress(f"[{fname}] Detecção de descontinuidades de fase...", progress_callback)
            results["analyses"]["phase"] = self._detect_phase_discontinuities(audio_data, sample_rate)
            
            # 6. Detecção de silêncio anômalo
            self._notify_progress(f"[{fname}] Detecção de silêncio anômalo...", progress_callback)
            results["analyses"]["silence"] = self._detect_anomalous_silence(audio_data, sample_rate)
            
        except Exception as e:
            self._log_error(e)
            results["status"] = "error"
            results["error"] = str(e)
        
        self._save_results(results, output_filename)
        return results
    
    def _extract_metadata(self, input_file: Path) -> dict[str, Any]:
        """Extrai metadados do arquivo de áudio via FFprobe."""
        try:
            cmd = [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", str(input_file)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            probe_data = json.loads(result.stdout)
            
            # Extrair informações relevantes
            format_info = probe_data.get("format", {})
            streams = probe_data.get("streams", [])
            
            audio_stream = next(
                (s for s in streams if s.get("codec_type") == "audio"),
                {}
            )
            
            metadata = {
                "format": format_info.get("format_name", "unknown"),
                "format_long": format_info.get("format_long_name", "unknown"),
                "duration_seconds": float(format_info.get("duration", 0)),
                "bitrate_kbps": int(format_info.get("bit_rate", 0)) // 1000,
                "size_bytes": int(format_info.get("size", 0)),
                "codec": audio_stream.get("codec_name", "unknown"),
                "codec_long": audio_stream.get("codec_long_name", "unknown"),
                "sample_rate": int(audio_stream.get("sample_rate", 0)),
                "channels": audio_stream.get("channels", 0),
                "channel_layout": audio_stream.get("channel_layout", "unknown"),
                "bits_per_sample": audio_stream.get("bits_per_sample", 0),
                "tags": format_info.get("tags", {}),
            }
            
            # Detectar possível software de edição nas tags
            tags = metadata["tags"]
            encoder_hints = []
            for key in ["encoder", "encoded_by", "software", "comment", "tool"]:
                if key in tags:
                    encoder_hints.append(f"{key}: {tags[key]}")
            
            metadata["encoder_hints"] = encoder_hints
            metadata["forensic_note"] = self._generate_metadata_note(metadata)
            
            return metadata
            
        except subprocess.CalledProcessError as e:
            _logger.error("FFprobe falhou: %s", e)
            return {"error": "FFprobe failed", "details": str(e)}
        except json.JSONDecodeError as e:
            _logger.error("Falha ao parsear JSON do FFprobe: %s", e)
            return {"error": "JSON parse error", "details": str(e)}
    
    def _generate_metadata_note(self, metadata: dict) -> str:
        """Gera nota forense baseada nos metadados."""
        notes = []
        
        # Verificar codec comum de mensageiros
        codec = metadata.get("codec", "").lower()
        if codec == "opus":
            notes.append("Codec Opus detectado (comum em WhatsApp, Telegram)")
        elif codec == "aac":
            notes.append("Codec AAC detectado (comum em iPhone, YouTube)")
        elif codec == "mp3":
            notes.append("Codec MP3 detectado (formato genérico)")
        
        # Verificar bitrate suspeito (muito baixo = recompressão múltipla)
        bitrate = metadata.get("bitrate_kbps", 0)
        if 0 < bitrate < 32:
            notes.append(f"Bitrate muito baixo ({bitrate} kbps) - possível recompressão múltipla")
        
        # Verificar hints de encoder
        if metadata.get("encoder_hints"):
            notes.append("Software de edição identificado nas tags")
        
        return "; ".join(notes) if notes else "Nenhuma anomalia evidente nos metadados"
    
    def _load_audio(self, input_file: Path) -> tuple[Optional[np.ndarray], int, Optional[str]]:
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
                return audio, sr, None
            
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
            return audio, sr, None
            
        except Exception as e:
            _logger.error("Falha ao carregar áudio: %s", e)
            return None, 0, str(e)
    
    def _analyze_spectral(self, audio: np.ndarray, sr: int) -> dict[str, Any]:
        """Analisa características espectrais do áudio (estatísticas apenas)."""
        import librosa
        
        # Calcular STFT
        stft = np.abs(librosa.stft(audio))
        
        # Frequências
        freqs = librosa.fft_frequencies(sr=sr)
        
        # Estatísticas espectrais
        spectral_centroid = librosa.feature.spectral_centroid(y=audio, sr=sr)[0]
        spectral_bandwidth = librosa.feature.spectral_bandwidth(y=audio, sr=sr)[0]
        spectral_rolloff = librosa.feature.spectral_rolloff(y=audio, sr=sr)[0]
        spectral_flatness = librosa.feature.spectral_flatness(y=audio)[0]
        
        # Zero crossing rate (indicador de ruído/silêncio)
        zcr = librosa.feature.zero_crossing_rate(audio)[0]
        
        # Energia por banda de frequência
        low_energy = np.mean(stft[:len(freqs)//4, :])  # 0-25% das freqs
        mid_energy = np.mean(stft[len(freqs)//4:len(freqs)//2, :])  # 25-50%
        high_energy = np.mean(stft[len(freqs)//2:, :])  # 50-100%
        
        # Detectar gaps espectrais (quedas abruptas de energia)
        energy_over_time = np.mean(stft, axis=0)
        energy_diff = np.diff(energy_over_time)
        significant_drops = np.sum(energy_diff < -np.std(energy_diff) * 3)
        
        # Frequência máxima útil (onde a energia cai significativamente)
        freq_spectrum = np.mean(stft, axis=1)
        threshold = np.max(freq_spectrum) * 0.01
        useful_freq_idx = np.where(freq_spectrum > threshold)[0]
        max_useful_freq = freqs[useful_freq_idx[-1]] if len(useful_freq_idx) > 0 else 0
        
        return {
            "centroid_hz": {
                "mean": float(np.mean(spectral_centroid)),
                "std": float(np.std(spectral_centroid)),
            },
            "bandwidth_hz": {
                "mean": float(np.mean(spectral_bandwidth)),
                "std": float(np.std(spectral_bandwidth)),
            },
            "rolloff_hz": {
                "mean": float(np.mean(spectral_rolloff)),
                "std": float(np.std(spectral_rolloff)),
            },
            "flatness": {
                "mean": float(np.mean(spectral_flatness)),
                "std": float(np.std(spectral_flatness)),
            },
            "zero_crossing_rate": {
                "mean": float(np.mean(zcr)),
                "std": float(np.std(zcr)),
            },
            "energy_distribution": self._safe_energy_distribution(low_energy, mid_energy, high_energy),
            "max_useful_frequency_hz": float(max_useful_freq),
            "significant_energy_drops": int(significant_drops),
            "forensic_note": self._generate_spectral_note(
                significant_drops, max_useful_freq, sr, float(np.mean(spectral_flatness))
            ),
        }
    
    def _safe_energy_distribution(self, low: float, mid: float, high: float) -> dict[str, float]:
        """Calcula distribuição de energia com proteção contra divisão por zero."""
        total = low + mid + high
        if total == 0 or np.isnan(total):
            return {"low_band_pct": 0.0, "mid_band_pct": 0.0, "high_band_pct": 0.0}
        return {
            "low_band_pct": float(low / total * 100),
            "mid_band_pct": float(mid / total * 100),
            "high_band_pct": float(high / total * 100),
        }
    
    def _generate_spectral_note(
        self, drops: int, max_freq: float, sr: int, flatness: float
    ) -> str:
        """Gera nota forense baseada na análise espectral."""
        notes = []
        
        if drops > 5:
            notes.append(f"{drops} quedas abruptas de energia detectadas (possíveis cortes)")
        
        # Verificar truncamento de frequência (indica compressão)
        nyquist = sr / 2
        if max_freq < nyquist * 0.8:
            notes.append(
                f"Espectro truncado em {max_freq/1000:.1f}kHz "
                f"(Nyquist: {nyquist/1000:.1f}kHz) - indica compressão"
            )
        
        if flatness > 0.5:
            notes.append("Alta uniformidade espectral - possível ruído ou síntese")
        
        return "; ".join(notes) if notes else "Características espectrais dentro do esperado"
    
    def _analyze_noise_consistency(self, audio: np.ndarray, sr: int) -> dict[str, Any]:
        """Analisa consistência do ruído de fundo (apenas estatísticas)."""
        import librosa
        
        # Dividir áudio em segmentos
        window_size = int(self.config.audio_noise_window * sr) if hasattr(self.config, 'audio_noise_window') else int(0.5 * sr)
        hop_size = window_size // 2
        
        # Calcular RMS por segmento
        rms = librosa.feature.rms(y=audio, frame_length=window_size, hop_length=hop_size)[0]
        rms_db = librosa.amplitude_to_db(rms + 1e-10)
        
        # Estatísticas do noise floor
        noise_floor = np.percentile(rms_db, 10)  # 10º percentil como estimativa do noise floor
        
        # Detectar variações bruscas no noise floor
        rms_diff = np.abs(np.diff(rms_db))
        threshold = np.mean(rms_diff) + 3 * np.std(rms_diff)
        abrupt_changes = np.sum(rms_diff > threshold)
        
        # Segmentar e comparar ruído em diferentes partes
        n_segments = 4
        segment_len = len(rms_db) // n_segments
        segment_floors = []
        for i in range(n_segments):
            start = i * segment_len
            end = start + segment_len
            segment_floors.append(float(np.percentile(rms_db[start:end], 10)))
        
        floor_variance = float(np.var(segment_floors))
        
        return {
            "noise_floor_db": float(noise_floor),
            "rms_mean_db": float(np.mean(rms_db)),
            "rms_std_db": float(np.std(rms_db)),
            "rms_range_db": float(np.max(rms_db) - np.min(rms_db)),
            "abrupt_level_changes": int(abrupt_changes),
            "segment_noise_floors_db": segment_floors,
            "segment_floor_variance": floor_variance,
            "forensic_note": self._generate_noise_note(
                abrupt_changes, floor_variance, segment_floors
            ),
        }
    
    def _generate_noise_note(
        self, abrupt_changes: int, floor_variance: float, segment_floors: list
    ) -> str:
        """Gera nota forense baseada na análise de ruído."""
        notes = []
        
        if abrupt_changes > 3:
            notes.append(
                f"{abrupt_changes} mudanças bruscas de nível detectadas "
                "(possível splicing ou edição)"
            )
        
        if floor_variance > 25:
            notes.append(
                f"Alta variação no ruído de fundo entre segmentos "
                f"(variância: {floor_variance:.1f} dB²) - indica origens diferentes"
            )
        
        # Verificar se há segmentos com ruído muito diferente
        floor_range = max(segment_floors) - min(segment_floors)
        if floor_range > 10:
            notes.append(
                f"Diferença de {floor_range:.1f}dB no noise floor entre segmentos"
            )
        
        return "; ".join(notes) if notes else "Ruído de fundo consistente ao longo do áudio"
    
    def _detect_phase_discontinuities(self, audio: np.ndarray, sr: int) -> dict[str, Any]:
        """Detecta descontinuidades de fase que indicam cortes."""
        import librosa
        
        # Calcular STFT com fase
        stft_complex = librosa.stft(audio)
        phase = np.angle(stft_complex)
        
        # Calcular diferença de fase entre frames consecutivos
        phase_diff = np.diff(phase, axis=1)
        
        # Normalizar diferença de fase para [-pi, pi]
        phase_diff = np.mod(phase_diff + np.pi, 2 * np.pi) - np.pi
        
        # Detectar saltos de fase significativos
        phase_jump_threshold = np.pi * 0.8  # 80% de pi
        
        # Média de saltos de fase por frame
        mean_phase_jumps = np.mean(np.abs(phase_diff) > phase_jump_threshold, axis=0)
        
        # Frames com muitos saltos simultâneos (provável corte)
        suspicious_frames = np.where(mean_phase_jumps > 0.3)[0]  # >30% das freqs com salto
        
        # Converter frames para tempo
        hop_length = 512  # librosa default
        suspicious_times = librosa.frames_to_time(suspicious_frames, sr=sr, hop_length=hop_length)
        
        # Agrupar detecções próximas
        discontinuities = []
        if len(suspicious_times) > 0:
            current_group = [suspicious_times[0]]
            for t in suspicious_times[1:]:
                if t - current_group[-1] < 0.1:  # Agrupar se < 100ms
                    current_group.append(t)
                else:
                    discontinuities.append({
                        "time_seconds": float(np.mean(current_group)),
                        "confidence": min(len(current_group) / 5, 1.0)  # Mais frames = mais confiança
                    })
                    current_group = [t]
            # Último grupo
            discontinuities.append({
                "time_seconds": float(np.mean(current_group)),
                "confidence": min(len(current_group) / 5, 1.0)
            })
        
        # Filtrar por confiança
        high_confidence = [d for d in discontinuities if d["confidence"] > 0.5]
        
        return {
            "total_suspicious_frames": len(suspicious_frames),
            "discontinuity_count": len(discontinuities),
            "high_confidence_count": len(high_confidence),
            "discontinuities": discontinuities[:20],  # Limitar para não sobrecarregar
            "forensic_note": self._generate_phase_note(len(high_confidence), discontinuities),
        }
    
    def _generate_phase_note(
        self, high_conf_count: int, discontinuities: list
    ) -> str:
        """Gera nota forense baseada na análise de fase."""
        if high_conf_count == 0:
            return "Nenhuma descontinuidade de fase significativa detectada"
        elif high_conf_count <= 2:
            return (
                f"{high_conf_count} possível(is) ponto(s) de corte detectado(s) - "
                "verificar manualmente"
            )
        else:
            return (
                f"{high_conf_count} descontinuidades de fase detectadas - "
                "alta probabilidade de edição/splicing"
            )
    
    def _detect_anomalous_silence(self, audio: np.ndarray, sr: int) -> dict[str, Any]:
        """Detecta segmentos de silêncio anômalo.
        
        Classifica silêncios digitais (zeros perfeitos) por posição:
        - start: início do áudio (comum em gravações de celular)
        - end: fim do áudio (comum em gravações de celular)
        - middle: meio do áudio (altamente suspeito)
        
        Em telefonia celular, silêncios são preenchidos por Comfort Noise (DTX),
        então zeros perfeitos no meio do áudio são especialmente anômalos.
        """
        import librosa
        
        # Calcular RMS
        frame_length = 2048
        hop_length = 512
        rms = librosa.feature.rms(y=audio, frame_length=frame_length, hop_length=hop_length)[0]
        rms_db = librosa.amplitude_to_db(rms + 1e-10)
        
        # Threshold para silêncio
        silence_threshold = getattr(self.config, 'audio_silence_threshold', -60.0)
        
        # Margem para início/fim (parametrizável)
        margin_seconds = getattr(self.config, 'audio_silence_margin_seconds', 1.0)
        total_duration = len(audio) / sr
        
        # Encontrar frames de silêncio
        silence_mask = rms_db < silence_threshold
        
        # Encontrar segmentos contínuos de silêncio
        silence_segments = []
        in_silence = False
        start_frame = 0
        
        for i, is_silent in enumerate(silence_mask):
            if is_silent and not in_silence:
                in_silence = True
                start_frame = i
            elif not is_silent and in_silence:
                in_silence = False
                duration_frames = i - start_frame
                if duration_frames > 2:  # Mínimo de ~20ms
                    start_time = librosa.frames_to_time(start_frame, sr=sr, hop_length=hop_length)
                    end_time = librosa.frames_to_time(i, sr=sr, hop_length=hop_length)
                    
                    # Verificar se é silêncio digital (valores muito próximos de zero)
                    start_sample = start_frame * hop_length
                    end_sample = min(i * hop_length, len(audio))
                    segment = audio[start_sample:end_sample]
                    
                    is_digital_silence = bool(np.max(np.abs(segment)) < 1e-6)
                    
                    # Classificar por posição
                    if start_time < margin_seconds:
                        position = "start"
                    elif end_time > (total_duration - margin_seconds):
                        position = "end"
                    else:
                        position = "middle"
                    
                    # Ajustar anomaly_score por posição e tipo
                    if is_digital_silence:
                        if position == "middle":
                            anomaly_score = 1.0  # Altamente suspeito
                        else:
                            anomaly_score = 0.2  # Comum em gravações de celular
                    else:
                        anomaly_score = 0.1  # Silêncio natural (não digital)
                    
                    silence_segments.append({
                        "start_seconds": float(start_time),
                        "end_seconds": float(end_time),
                        "duration_seconds": float(end_time - start_time),
                        "is_digital_silence": is_digital_silence,
                        "position": position,
                        "anomaly_score": anomaly_score
                    })
        
        # Se terminou em silêncio
        if in_silence:
            start_time = librosa.frames_to_time(start_frame, sr=sr, hop_length=hop_length)
            end_time = librosa.frames_to_time(len(silence_mask), sr=sr, hop_length=hop_length)
            
            # Verificar posição
            if start_time < margin_seconds:
                position = "start"
            elif end_time > (total_duration - margin_seconds):
                position = "end"
            else:
                position = "middle"
            
            silence_segments.append({
                "start_seconds": float(start_time),
                "end_seconds": float(end_time),
                "duration_seconds": float(end_time - start_time),
                "is_digital_silence": False,
                "position": position,
                "anomaly_score": 0.1
            })
        
        # Estatísticas
        total_silence = sum(s["duration_seconds"] for s in silence_segments)
        digital_silences = [s for s in silence_segments if s["is_digital_silence"]]
        digital_middle = [s for s in digital_silences if s["position"] == "middle"]
        digital_edges = [s for s in digital_silences if s["position"] in ("start", "end")]
        
        return {
            "silence_count": len(silence_segments),
            "total_silence_seconds": float(total_silence),
            "silence_percentage": float(total_silence / (len(audio) / sr) * 100),
            "digital_silence_count": len(digital_silences),
            "digital_middle_count": len(digital_middle),
            "digital_edge_count": len(digital_edges),
            "segments": silence_segments[:20],  # Limitar
            "forensic_note": self._generate_silence_note(
                len(silence_segments), len(digital_middle), len(digital_edges), total_silence
            ),
        }
    
    def _generate_silence_note(
        self, total_count: int, digital_middle_count: int, digital_edge_count: int, total_duration: float
    ) -> str:
        """Gera nota forense baseada na análise de silêncio.
        
        Diferencia zeros digitais por posição:
        - middle: altamente suspeito (não natural)
        - start/end: comum em gravações de celular (menos suspeito)
        
        Em telefonia celular, silêncios são preenchidos por Comfort Noise (DTX),
        então zeros perfeitos no meio do áudio são especialmente anômalos.
        """
        notes = []
        
        if digital_middle_count > 0:
            notes.append(
                f"{digital_middle_count} segmento(s) de silêncio digital no MEIO do áudio - "
                "altamente suspeito de inserção artificial ou manipulação. "
                "Em telefonia celular, silêncios são preenchidos por Comfort Noise (DTX), "
                "não por zeros perfeitos."
            )
        
        if digital_edge_count > 0:
            notes.append(
                f"{digital_edge_count} segmento(s) de silêncio digital no início/fim - "
                "comportamento comum em gravações de apps nativos de celular (lead-in/lead-out). "
                "A duração desses zeros pode variar conforme SO, versão e modelo do dispositivo."
            )
        
        if total_count > 10:
            notes.append(
                f"Alto número de pausas ({total_count}) - verificar se são naturais"
            )
        
        return "; ".join(notes) if notes else "Padrões de silêncio dentro do esperado"
