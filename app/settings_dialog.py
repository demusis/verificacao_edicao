import json
from pathlib import Path
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QSpinBox, QDoubleSpinBox, QComboBox, 
                               QPushButton, QTabWidget, QWidget, QFormLayout, QMessageBox)
from PySide6.QtCore import Qt

CONFIG_FILE = Path("config.json")

DEFAULT_CONFIG = {
    "copymove_features": 2000,
    "copymove_min_cluster": 4,
    "resampling_block_size": 64,
    "prnu_frame_limit": 50,
    "ela_quality": 90
}

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configurações Avançadas")
        self.resize(400, 300)
        self.config = self.load_config()
        self.init_ui()

    def load_config(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    # Merge with default ensuring all keys exist
                    config = DEFAULT_CONFIG.copy()
                    config.update(data)
                    return config
            except:
                pass
        return DEFAULT_CONFIG.copy()

    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao salvar configurações: {e}")

    def init_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        
        # --- Helper para adicionar linha com ajuda ---
        def add_param(form_layout, label, widget, help_msg):
            h_layout = QHBoxLayout()
            h_layout.addWidget(widget)
            
            btn_help = QPushButton("?")
            btn_help.setFixedSize(25, 25)
            # Usar closure para capturar a mensagem atual
            # Necessário bindar o texto no lambda default arg
            btn_help.clicked.connect(lambda checked=False, txt=help_msg: QMessageBox.information(self, "Ajuda do Parâmetro", txt))
            
            h_layout.addWidget(btn_help)
            form_layout.addRow(label, h_layout)

        # --- TAB: Imagem ---
        tab_img = QWidget()
        form_img = QFormLayout(tab_img)
        
        self.spin_cm_features = QSpinBox()
        self.spin_cm_features.setRange(500, 10000)
        self.spin_cm_features.setSingleStep(100)
        self.spin_cm_features.setValue(int(self.config.get('copymove_features', 2000)))
        
        msg_cm_feat = (
            "<b>Sensibilidade (Pontos SIFT)</b><br><br>"
            "Define a quantidade máxima de pontos de interesse que o algoritmo busca na imagem.<br><br>"
            "<ul>"
            "<li><b>Alto (5000+):</b> Máxima sensibilidade. Detecta clonagens muito pequenas ou bem disfarçadas. "
            "Pode tornar a análise lenta.</li>"
            "<li><b>Baixo (1000):</b> Mais rápido, focado apenas em clonagens óbvias.</li>"
            "</ul>"
        )
        add_param(form_img, "Sensibilidade (Pontos SIFT):", self.spin_cm_features, msg_cm_feat)
        
        self.spin_cm_cluster = QSpinBox()
        self.spin_cm_cluster.setRange(2, 20)
        self.spin_cm_cluster.setValue(int(self.config.get('copymove_min_cluster', 4)))
        
        msg_cm_clus = (
            "<b>Rigor (Mínimo de Cluster)</b><br><br>"
            "Define quantos vetores idênticos (pontos coincidentes) são necessários para confirmar uma clonagem.<br><br>"
            "<ul>"
            "<li><b>Baixo (2-3):</b> Muito sensível. Detecta qualquer repetição mínima. "
            "Risco alto de Falso Positivo em texturas naturais (ex: grama, areia, cabelo).</li>"
            "<li><b>Alto (5+):</b> Mais rigoroso. Só confirma se houver uma área duplicada significativa.</li>"
            "</ul>"
        )
        add_param(form_img, "Rigor (Mínimo de Cluster):", self.spin_cm_cluster, msg_cm_clus)
        
        self.spin_res_block = QComboBox()
        self.spin_res_block.addItems(["32", "64", "128"])
        curr_blk = str(self.config.get('resampling_block_size', 64))
        self.spin_res_block.setCurrentText(curr_blk)
        
        msg_res = (
             "<b>Tamanho do Bloco (Resampling)</b><br><br>"
             "Janela de análise para detectar padrões periódicos de interpolação.<br><br>"
             "<ul>"
             "<li><b>32:</b> Ideal para detectar edições pequenas e muito localizadas. Mais ruído.</li>"
             "<li><b>64/128:</b> Padrão equilibrado. Melhor para detectar se a imagem inteira foi redimensionada.</li>"
             "</ul>"
        )
        add_param(form_img, "Tamanho do Bloco:", self.spin_res_block, msg_res)
        
        self.spin_ela_qual = QSpinBox()
        self.spin_ela_qual.setRange(50, 100)
        self.spin_ela_qual.setValue(int(self.config.get('ela_quality', 90)))
        
        msg_ela = (
            "<b>Qualidade ELA</b><br><br>"
            "Qualidade JPEG usada para gerar a imagem de erro.<br>"
            "Padrão: 90 ou 95. Alterar apenas se souber o que está fazendo."
        )
        add_param(form_img, "Qualidade ELA:", self.spin_ela_qual, msg_ela)
        
        tabs.addTab(tab_img, "Análise de Imagem")
        
        # --- TAB: Vídeo ---
        tab_vid = QWidget()
        form_vid = QFormLayout(tab_vid)
        
        self.spin_prnu_frames = QSpinBox()
        self.spin_prnu_frames.setRange(10, 500)
        self.spin_prnu_frames.setValue(int(self.config.get('prnu_frame_limit', 50)))
        
        msg_prnu = (
            "<b>Limite de Quadros (PRNU)</b><br><br>"
            "Quantidade de frames do vídeo usados para extrair a assinatura do sensor da câmera.<br><br>"
            "<ul>"
            "<li><b>Mais Quadros (100+):</b> Assinatura mais precisa e robusta. Processamento mais lento.</li>"
            "<li><b>Menos Quadros (20-50):</b> Processamento rápido. Suficiente para comparação básica.</li>"
            "</ul>"
        )
        add_param(form_vid, "Limite de Quadros (PRNU):", self.spin_prnu_frames, msg_prnu)
        
        tabs.addTab(tab_vid, "Vídeo e PRNU")

        # --- TAB: Deepfake / Forense ---
        tab_df = QWidget()
        form_df = QFormLayout(tab_df)
        
        # 1. Noise Threshold
        self.spin_df_noise = QSpinBox()
        self.spin_df_noise.setRange(10, 90)
        self.spin_df_noise.setValue(int(self.config.get('deepfake_noise_threshold', 50)))
        
        msg_df_noise = (
            "<b>Susceptibilidade a Ruído (%)</b><br><br>"
            "Define a diferença percentual de ruído aceitável entre sujeito e fundo.<br><br>"
            "<ul>"
            "<li><b>Baixo (30%):</b> Muito rigoroso. Qualquer diferença mínima gera alerta.</li>"
            "<li><b>Alto (70%):</b> Mais tolerante. Evita falsos positivos em imagens ruidosas (ISO alto).</li>"
            "</ul>"
        )
        add_param(form_df, "Susceptibilidade a Ruído (%):", self.spin_df_noise, msg_df_noise)
        
        # 2. Jitter Threshold
        self.spin_df_jitter = QSpinBox()
        self.spin_df_jitter.setRange(5, 50)
        self.spin_df_jitter.setValue(int(self.config.get('deepfake_jitter_threshold', 15)))
        
        msg_df_jitter = (
            "<b>Sensibilidade de Jitter (Vídeo)</b><br><br>"
            "Limite de variação temporal dos scores forensic.<br><br>"
            "<ul>"
            "<li><b>Baixo (5-10):</b> Hiper-sensível a qualquer oscilação de qualidade.</li>"
            "<li><b>Alto (20+):</b> Ignora variações naturais de iluminação/compressão.</li>"
            "</ul>"
        )
        add_param(form_df, "Sensibilidade de Jitter:", self.spin_df_jitter, msg_df_jitter)
        
        # 3. Fast Mode
        from PySide6.QtWidgets import QCheckBox
        self.chk_df_fast = QCheckBox("Ativar Modo Rápido")
        self.chk_df_fast.setChecked(bool(self.config.get('deepfake_fast_mode', False)))
        
        msg_df_fast = (
            "<b>Modo Rápido (Apenas Consistência Física)</b><br><br>"
            "Se marcado, PULA as análises pesadas de FFT (Frequência) e LBP (Textura) frame-a-frame.<br>"
            "Foca apenas na detecção de emendas (Splicing) e ruído.<br>"
            "Recomendado para vídeos muito longos ou 4K."
        )
        add_param(form_df, "Scanner Rápido:", self.chk_df_fast, msg_df_fast)
        
        tabs.addTab(tab_df, "Deepfake/Forense")
        
        layout.addWidget(tabs)
        
        # Buttons
        btn_box = QHBoxLayout()
        btn_save = QPushButton("Salvar")
        btn_save.clicked.connect(self.on_save)
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        
        btn_box.addStretch()
        btn_box.addWidget(btn_save)
        btn_box.addWidget(btn_cancel)
        
        layout.addLayout(btn_box)

    def on_save(self):
        # Update config dict
        self.config['copymove_features'] = self.spin_cm_features.value()
        self.config['copymove_min_cluster'] = self.spin_cm_cluster.value()
        self.config['resampling_block_size'] = int(self.spin_res_block.currentText())
        self.config['ela_quality'] = self.spin_ela_qual.value()
        self.config['prnu_frame_limit'] = self.spin_prnu_frames.value()
        self.config['deepfake_noise_threshold'] = self.spin_df_noise.value()
        self.config['deepfake_jitter_threshold'] = self.spin_df_jitter.value()
        self.config['deepfake_fast_mode'] = self.chk_df_fast.isChecked()
        
        self.save_config()
        self.accept()
