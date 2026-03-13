"""
Diálogo de configurações avançadas para a GUI.

Este módulo fornece uma interface gráfica para ajustar os parâmetros
de análise forense, usando AnalysisConfig como backend.
"""
import json
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox,
    QPushButton, QTabWidget, QWidget, QFormLayout, QMessageBox
)
from PySide6.QtCore import Qt

from core.config_schema import AnalysisConfig, DEFAULT_CONFIG

_logger = logging.getLogger(__name__)

CONFIG_FILE = Path("config.json")


def load_config() -> AnalysisConfig:
    """Carrega configuração do arquivo JSON ou retorna padrão.
    
    Returns:
        AnalysisConfig com valores do arquivo ou padrões.
    """
    if CONFIG_FILE.exists():
        try:
            return AnalysisConfig.from_json_file(CONFIG_FILE)
        except Exception as e:
            _logger.warning("Erro ao carregar config.json: %s", e)
    
    # Se não existir ou houver erro, criar arquivo com padrões
    try:
        DEFAULT_CONFIG.save_to_json(CONFIG_FILE)
    except Exception as e:
        _logger.warning("Erro ao criar config.json padrão: %s", e)
    
    return AnalysisConfig()


def save_config(config: AnalysisConfig) -> bool:
    """Salva configuração em arquivo JSON.
    
    Args:
        config: Configuração a ser salva.
        
    Returns:
        True se salvou com sucesso, False caso contrário.
    """
    try:
        config.save_to_json(CONFIG_FILE)
        return True
    except Exception as e:
        _logger.error("Erro ao salvar config.json: %s", e)
        return False


class SettingsDialog(QDialog):
    """Diálogo de configurações avançadas."""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Configurações Avançadas")
        self.resize(400, 300)
        self.config = load_config()
        self._init_ui()
    
    def get_config(self) -> AnalysisConfig:
        """Retorna a configuração atual (após edições)."""
        return self.config
    
    def _save_config(self) -> None:
        """Salva configuração atual no arquivo."""
        if not save_config(self.config):
            QMessageBox.critical(
                self, "Erro", 
                "Falha ao salvar configurações. Verifique permissões do arquivo."
            )
    
    def _init_ui(self) -> None:
        """Inicializa a interface do usuário."""
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        
        def add_param(
            form_layout: QFormLayout, 
            label: str, 
            widget: QWidget, 
            help_msg: str
        ) -> None:
            """Adiciona um parâmetro com botão de ajuda."""
            h_layout = QHBoxLayout()
            h_layout.addWidget(widget)
            
            btn_help = QPushButton("?")
            btn_help.setFixedSize(25, 25)
            btn_help.clicked.connect(
                lambda checked=False, txt=help_msg: 
                    QMessageBox.information(self, "Ajuda do Parâmetro", txt)
            )
            
            h_layout.addWidget(btn_help)
            form_layout.addRow(label, h_layout)
        
        # --- TAB: Imagem ---
        tab_img = QWidget()
        form_img = QFormLayout(tab_img)
        
        self.spin_cm_features = QSpinBox()
        self.spin_cm_features.setRange(500, 10000)
        self.spin_cm_features.setSingleStep(100)
        self.spin_cm_features.setValue(self.config.copymove_features)
        
        msg_cm_feat = (
            "<b>Sensibilidade (Pontos SIFT)</b><br><br>"
            "Define a quantidade máxima de pontos de interesse.<br><br>"
            "<ul>"
            "<li><b>Alto (5000+):</b> Máxima sensibilidade. Pode ser lento.</li>"
            "<li><b>Baixo (1000):</b> Mais rápido, clonagens óbvias.</li>"
            "</ul>"
        )
        add_param(form_img, "Sensibilidade (Pontos SIFT):", self.spin_cm_features, msg_cm_feat)
        
        self.spin_cm_cluster = QSpinBox()
        self.spin_cm_cluster.setRange(2, 20)
        self.spin_cm_cluster.setValue(self.config.copymove_min_cluster)
        
        msg_cm_clus = (
            "<b>Rigor (Mínimo de Cluster)</b><br><br>"
            "Quantos pontos coincidentes para confirmar clonagem.<br><br>"
            "<ul>"
            "<li><b>Baixo (3-5):</b> Sensível, risco de falso positivo.</li>"
            "<li><b>Alto (8+):</b> Rigoroso, recomendado.</li>"
            "</ul>"
        )
        add_param(form_img, "Rigor (Mínimo de Cluster):", self.spin_cm_cluster, msg_cm_clus)
        
        self.spin_res_block = QComboBox()
        self.spin_res_block.addItems(["32", "64", "128"])
        self.spin_res_block.setCurrentText(str(self.config.resampling_block_size))
        
        msg_res = (
            "<b>Tamanho do Bloco (Resampling)</b><br><br>"
            "Janela de análise para detectar interpolação.<br><br>"
            "<ul>"
            "<li><b>32:</b> Edições pequenas e localizadas.</li>"
            "<li><b>64/128:</b> Redimensionamento geral.</li>"
            "</ul>"
        )
        add_param(form_img, "Tamanho do Bloco:", self.spin_res_block, msg_res)
        
        self.spin_ela_qual = QSpinBox()
        self.spin_ela_qual.setRange(50, 100)
        self.spin_ela_qual.setValue(self.config.ela_quality)
        
        msg_ela = (
            "<b>Qualidade ELA</b><br><br>"
            "Qualidade JPEG para gerar imagem de erro.<br>"
            "Padrão: 90. Alterar apenas se necessário."
        )
        add_param(form_img, "Qualidade ELA:", self.spin_ela_qual, msg_ela)
        
        tabs.addTab(tab_img, "Análise de Imagem")
        
        # --- TAB: Vídeo ---
        tab_vid = QWidget()
        form_vid = QFormLayout(tab_vid)
        
        self.spin_prnu_frames = QSpinBox()
        self.spin_prnu_frames.setRange(10, 500)
        self.spin_prnu_frames.setValue(self.config.prnu_frame_limit)
        
        msg_prnu = (
            "<b>Limite de Quadros (PRNU)</b><br><br>"
            "Frames usados para extrair assinatura do sensor.<br><br>"
            "<ul>"
            "<li><b>Mais (100+):</b> Preciso, lento.</li>"
            "<li><b>Menos (20-50):</b> Rápido, comparação básica.</li>"
            "</ul>"
        )
        add_param(form_vid, "Limite de Quadros (PRNU):", self.spin_prnu_frames, msg_prnu)
        
        tabs.addTab(tab_vid, "Vídeo e PRNU")
        
        # --- TAB: Deepfake ---
        tab_df = QWidget()
        form_df = QFormLayout(tab_df)
        
        self.spin_df_noise = QSpinBox()
        self.spin_df_noise.setRange(10, 90)
        self.spin_df_noise.setValue(self.config.deepfake_noise_threshold)
        
        msg_df_noise = (
            "<b>Susceptibilidade a Ruído (%)</b><br><br>"
            "Diferença de ruído aceitável entre sujeito e fundo.<br><br>"
            "<ul>"
            "<li><b>Baixo (30%):</b> Rigoroso, qualquer diferença gera alerta.</li>"
            "<li><b>Alto (70%):</b> Tolerante, evita falsos positivos.</li>"
            "</ul>"
        )
        add_param(form_df, "Susceptibilidade a Ruído (%):", self.spin_df_noise, msg_df_noise)
        
        self.spin_df_jitter = QSpinBox()
        self.spin_df_jitter.setRange(5, 50)
        self.spin_df_jitter.setValue(self.config.deepfake_jitter_threshold)
        
        msg_df_jitter = (
            "<b>Sensibilidade de Jitter (Vídeo)</b><br><br>"
            "Limite de variação temporal dos scores.<br><br>"
            "<ul>"
            "<li><b>Baixo (5-10):</b> Sensível a oscilações.</li>"
            "<li><b>Alto (20+):</b> Ignora variações naturais.</li>"
            "</ul>"
        )
        add_param(form_df, "Sensibilidade de Jitter:", self.spin_df_jitter, msg_df_jitter)
        
        self.chk_df_fast = QCheckBox("Ativar Modo Rápido")
        self.chk_df_fast.setChecked(self.config.deepfake_fast_mode)
        
        msg_df_fast = (
            "<b>Modo Rápido</b><br><br>"
            "Pula análises pesadas (FFT/LBP frame-a-frame).<br>"
            "Foca apenas em consistência física.<br>"
            "Recomendado para vídeos longos ou 4K."
        )
        add_param(form_df, "Scanner Rápido:", self.chk_df_fast, msg_df_fast)
        
        tabs.addTab(tab_df, "Deepfake/Forense")
        
        # --- TAB: Relatório ---
        tab_rep = QWidget()
        form_rep = QFormLayout(tab_rep)
        
        self.chk_rep_struct = QCheckBox("Estrutura do Arquivo (Vídeo)")
        self.chk_rep_struct.setChecked(self.config.report_structure)
        form_rep.addRow(self.chk_rep_struct)
        
        self.chk_rep_gop = QCheckBox("Estrutura de Compressão GOP (Vídeo)")
        self.chk_rep_gop.setChecked(self.config.report_gop)
        form_rep.addRow(self.chk_rep_gop)
        
        self.chk_rep_benford = QCheckBox("Análise Estatística Benford/FFT (Vídeo)")
        self.chk_rep_benford.setChecked(self.config.report_benford)
        form_rep.addRow(self.chk_rep_benford)
        
        self.chk_rep_quant = QCheckBox("Análise de Quantização (Vídeo)")
        self.chk_rep_quant.setChecked(self.config.report_quantization)
        form_rep.addRow(self.chk_rep_quant)
        
        self.chk_rep_prnu = QCheckBox("Identificação de Fonte PRNU (Vídeo/Imagem)")
        self.chk_rep_prnu.setChecked(self.config.report_prnu)
        form_rep.addRow(self.chk_rep_prnu)
        
        self.chk_rep_df = QCheckBox("Detecção de Deepfake/IA (Vídeo/Imagem)")
        self.chk_rep_df.setChecked(self.config.report_deepfake)
        form_rep.addRow(self.chk_rep_df)
        
        # Opções GERAIS do Relatório
        self.chk_rep_indiv = QCheckBox("Gerar Relatório Individual (1 PDF por Arquivo)")
        self.chk_rep_indiv.setChecked(self.config.report_individual)
        form_rep.addRow(self.chk_rep_indiv)
        
        self.chk_rep_ela = QCheckBox("Análise de Nível de Erro - ELA (Imagem)")
        self.chk_rep_ela.setChecked(self.config.report_ela)
        form_rep.addRow(self.chk_rep_ela)
        
        self.chk_rep_noise = QCheckBox("Consistência de Ruído (Imagem)")
        self.chk_rep_noise.setChecked(self.config.report_noise)
        form_rep.addRow(self.chk_rep_noise)
        
        self.chk_rep_cm = QCheckBox("Detecção de Clonagem - Copy-Move (Imagem)")
        self.chk_rep_cm.setChecked(self.config.report_copymove)
        form_rep.addRow(self.chk_rep_cm)
        
        self.chk_rep_res = QCheckBox("Detecção de Resampling/Escalonamento (Imagem)")
        self.chk_rep_res.setChecked(self.config.report_resampling)
        form_rep.addRow(self.chk_rep_res)
        
        self.chk_rep_ghost = QCheckBox("Análise de JPEG Ghosts (Imagem)")
        self.chk_rep_ghost.setChecked(self.config.report_jpeg_ghosts)
        form_rep.addRow(self.chk_rep_ghost)
        
        # Audio Report Checkboxes
        self.chk_rep_audio_meta = QCheckBox("Metadados de Áudio")
        self.chk_rep_audio_meta.setChecked(self.config.report_audio_metadata)
        form_rep.addRow(self.chk_rep_audio_meta)
        
        self.chk_rep_audio_spectral = QCheckBox("Análise Espectral (Áudio)")
        self.chk_rep_audio_spectral.setChecked(self.config.report_audio_spectral)
        form_rep.addRow(self.chk_rep_audio_spectral)
        
        self.chk_rep_audio_phase = QCheckBox("Descontinuidade de Fase (Áudio)")
        self.chk_rep_audio_phase.setChecked(self.config.report_audio_phase)
        form_rep.addRow(self.chk_rep_audio_phase)
        
        self.chk_rep_audio_silence = QCheckBox("Silêncio Anômalo (Áudio)")
        self.chk_rep_audio_silence.setChecked(self.config.report_audio_silence)
        form_rep.addRow(self.chk_rep_audio_silence)
        
        self.chk_rep_audio_df = QCheckBox("Deepfake de Voz (Áudio)")
        self.chk_rep_audio_df.setChecked(self.config.report_audio_deepfake)
        form_rep.addRow(self.chk_rep_audio_df)
        
        tabs.addTab(tab_rep, "Exibição no Relatório")
        
        # --- TAB: Áudio ---
        tab_audio = QWidget()
        form_audio = QFormLayout(tab_audio)
        
        self.spin_audio_noise_window = QDoubleSpinBox()
        self.spin_audio_noise_window.setRange(0.1, 2.0)
        self.spin_audio_noise_window.setSingleStep(0.1)
        self.spin_audio_noise_window.setValue(self.config.audio_noise_window)
        
        msg_noise_win = (
            "<b>Janela de Análise de Ruído</b><br><br>"
            "Duração em segundos para análise de noise floor.<br><br>"
            "<ul>"
            "<li><b>0.5s:</b> Padrão, bom equilíbrio.</li>"
            "<li><b>0.1-0.3s:</b> Detecta mudanças rápidas.</li>"
            "<li><b>1.0s+:</b> Ignora ruídos transitórios.</li>"
            "</ul>"
        )
        add_param(form_audio, "Janela de Ruído (s):", self.spin_audio_noise_window, msg_noise_win)
        
        self.spin_audio_silence = QSpinBox()
        self.spin_audio_silence.setRange(-80, -30)
        self.spin_audio_silence.setValue(int(self.config.audio_silence_threshold))
        
        msg_silence = (
            "<b>Limiar de Silêncio (dB)</b><br><br>"
            "Nível abaixo do qual é considerado silêncio.<br><br>"
            "<ul>"
            "<li><b>-60dB:</b> Padrão, detecta silêncio real.</li>"
            "<li><b>-40dB:</b> Mais tolerante a ruído ambiente.</li>"
            "<li><b>-70dB:</b> Muito sensível, pode gerar falsos positivos.</li>"
            "</ul>"
        )
        add_param(form_audio, "Limiar de Silêncio (dB):", self.spin_audio_silence, msg_silence)
        
        self.spin_audio_seg_dur = QDoubleSpinBox()
        self.spin_audio_seg_dur.setRange(5.0, 120.0)
        self.spin_audio_seg_dur.setSingleStep(5.0)
        self.spin_audio_seg_dur.setValue(self.config.audio_segment_duration)
        
        msg_seg_dur = (
            "<b>Duração do Segmento de Áudio (X)</b><br><br>"
            "Duração em segundos para cada trecho analisado.<br>"
            "Usado para início, fim e trechos aleatórios.<br><br>"
            "<ul>"
            "<li><b>20s:</b> Padrão, boa performance.</li>"
            "<li><b>60s:</b> Mais rigoroso, mais lento.</li>"
            "</ul>"
        )
        add_param(form_audio, "Duração do Segmento (s):", self.spin_audio_seg_dur, msg_seg_dur)
        
        self.spin_audio_rnd_seg = QSpinBox()
        self.spin_audio_rnd_seg.setRange(0, 20)
        self.spin_audio_rnd_seg.setValue(self.config.audio_random_segments)
        
        msg_rnd_seg = (
            "<b>Segmentos Aleatórios (N)</b><br><br>"
            "Quantidade de trechos aleatórios extraídos do meio do áudio.<br>"
            "Aumenta a cobertura da análise em arquivos longos.<br><br>"
            "<ul>"
            "<li><b>0:</b> Apenas início e fim.</li>"
            "<li><b>3:</b> Padrão, boa cobertura estatística.</li>"
            "<li><b>10+:</b> Varredura intensiva.</li>"
            "</ul>"
        )
        add_param(form_audio, "Trechos Aleatórios (N):", self.spin_audio_rnd_seg, msg_rnd_seg)
        
        self.spin_audio_silence_margin = QDoubleSpinBox()
        self.spin_audio_silence_margin.setRange(0.1, 5.0)
        self.spin_audio_silence_margin.setSingleStep(0.1)
        self.spin_audio_silence_margin.setValue(self.config.audio_silence_margin_seconds)
        
        msg_silence_margin = (
            "<b>Margem para Zeros no Início/Fim (s)</b><br><br>"
            "Define a margem de tempo no início e fim do áudio onde<br>"
            "zeros digitais são considerados normais (lead-in/lead-out).<br><br>"
            "<ul>"
            "<li><b>1.0s:</b> Padrão, cobre a maioria dos apps de celular.</li>"
            "<li><b>0.5s:</b> Mais rigoroso, menos tolerância a zeros.</li>"
            "<li><b>2.0s+:</b> Tolerante para gravações com inicialização lenta.</li>"
            "</ul>"
            "<br>Zeros digitais <b>fora</b> dessa margem (no meio do áudio)<br>"
            "são considerados altamente suspeitos."
        )
        add_param(form_audio, "Margem para Zeros (s):", self.spin_audio_silence_margin, msg_silence_margin)
        
        tabs.addTab(tab_audio, "Análise de Áudio")
        
        layout.addWidget(tabs)
        
        # Buttons
        btn_box = QHBoxLayout()
        btn_save = QPushButton("Salvar")
        btn_save.clicked.connect(self._on_save)
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        
        btn_box.addStretch()
        btn_box.addWidget(btn_save)
        btn_box.addWidget(btn_cancel)
        
        layout.addLayout(btn_box)
    
    def _on_save(self) -> None:
        """Callback para salvar configurações."""
        # Update config from widgets
        self.config = AnalysisConfig(
            # Image
            copymove_features=self.spin_cm_features.value(),
            copymove_min_cluster=self.spin_cm_cluster.value(),
            resampling_block_size=int(self.spin_res_block.currentText()),
            ela_quality=self.spin_ela_qual.value(),
            # Video
            prnu_frame_limit=self.spin_prnu_frames.value(),
            # Deepfake
            deepfake_noise_threshold=self.spin_df_noise.value(),
            deepfake_jitter_threshold=self.spin_df_jitter.value(),
            deepfake_fast_mode=self.chk_df_fast.isChecked(),
            # Report
            report_structure=self.chk_rep_struct.isChecked(),
            report_gop=self.chk_rep_gop.isChecked(),
            report_benford=self.chk_rep_benford.isChecked(),
            report_quantization=self.chk_rep_quant.isChecked(),
            report_prnu=self.chk_rep_prnu.isChecked(),
            report_deepfake=self.chk_rep_df.isChecked(),
            report_ela=self.chk_rep_ela.isChecked(),
            report_individual=self.chk_rep_indiv.isChecked(),
            report_noise=self.chk_rep_noise.isChecked(),
            report_copymove=self.chk_rep_cm.isChecked(),
            report_resampling=self.chk_rep_res.isChecked(),
            report_jpeg_ghosts=self.chk_rep_ghost.isChecked(),
            # Audio
            audio_noise_window=self.spin_audio_noise_window.value(),
            audio_silence_threshold=float(self.spin_audio_silence.value()),
            audio_segment_duration=self.spin_audio_seg_dur.value(),
            audio_random_segments=self.spin_audio_rnd_seg.value(),
            audio_silence_margin_seconds=self.spin_audio_silence_margin.value(),
            report_audio_metadata=self.chk_rep_audio_meta.isChecked(),
            report_audio_spectral=self.chk_rep_audio_spectral.isChecked(),
            report_audio_phase=self.chk_rep_audio_phase.isChecked(),
            report_audio_silence=self.chk_rep_audio_silence.isChecked(),
            report_audio_deepfake=self.chk_rep_audio_df.isChecked(),
        )
        
        self._save_config()
        self.accept()
