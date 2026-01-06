import sys
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                               QFileDialog, QTextEdit, QProgressBar, QMessageBox)
from PySide6.QtCore import Qt, QThread, Signal

import os

# Permitir execução direta sem -m
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Importações do Core e Modules
from core.case_manager import CaseManager
from modules.file_analysis import FileAnalysisModule
from modules.continuity import ContinuityModule
from modules.compression_analysis import CompressionAnalysisModule
from modules.prnu_analysis import PrnuAnalysisModule
from modules.quantization_analysis import QuantizationAnalysisModule
from modules.structure_analysis import StructureAnalysisModule
from modules.image_forensics import ImageForensicsModule # NEW
from modules.deepfake_analysis import DeepfakeAnalysisModule # NEW
from app.settings_dialog import SettingsDialog, DEFAULT_CONFIG

from modules.reporting import ReportingModule
import json

class AnalysisWorker(QThread):
    """Worker para executar a análise em background sem travar a GUI."""
    progress = Signal(str)
    finished = Signal(bool, str) # success, message


    
    def __init__(self, input_files: list[Path], output_dir: Path, case_name: str = None, config: dict = None):
        super().__init__()
        self.input_files = input_files
        self.output_dir = output_dir
        self.config = config or {}
        self.case_name = case_name
        
    def _is_video(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv']

    def run(self):
        try:
            # Nome do caso baseado no primeiro arquivo ou genérico se forem vários
            # Nome do caso recebido ou gerado automaticamente (fallback)
            if self.case_name:
                case_name = self.case_name
            elif len(self.input_files) == 1:
                case_name = f"case_{self.input_files[0].stem}"
            else:
                case_name = f"case_BATCH_{len(self.input_files)}_FILES_{self.input_files[0].stem}"
                
            self.progress.emit(f"Iniciando caso: {case_name}")
            
            # Setup com diretório personalizado
            cm = CaseManager(case_name, base_dir=self.output_dir)
            cm.setup()
            self.progress.emit(f"Diretório do caso: {cm.case_dir}")

            batch_manifest = []
            prnu_fingerprints = [] # List of tuples: (filename, npy_path)
            
            for idx, input_file in enumerate(self.input_files):
                self.progress.emit(f"--- Processando Arquivo {idx+1}/{len(self.input_files)}: {input_file.name} ---")
                
                # Prefixos para evitar sobreescrita
                prefix = f"{idx+1:02d}_{input_file.stem}"
                is_video = self._is_video(input_file)
                
                manifest_entry = {
                    "filename": input_file.name,
                    "type": "video" if is_video else "image",
                    "analysis_files": {}
                }
                
                if is_video:
                    # === FLUXO DE VÍDEO ===
                    
                    # Nomes de saída
                    out_fa = f"{prefix}_file_analysis.json"
                    out_cont = f"{prefix}_continuity.json"
                    out_comp = f"{prefix}_compression.json"
                    out_prnu = f"{prefix}_prnu.json"
                    out_struct = f"{prefix}_structure.json"
                    out_quant = f"{prefix}_quantization.json"
                    
                # === THUMBNAIL GENERATION ===
                thumb_filename = f"thumb_{input_file.stem}.jpg"
                thumb_path = cm.results_dir / thumb_filename
                
                try:
                    if is_video:
                        # Extract first frame
                        import subprocess
                        subprocess.run([
                            "ffmpeg", "-y", "-i", str(input_file), 
                            "-vframes", "1", "-update", "1", "-q:v", "2", 
                            str(thumb_path)
                        ], check=False)
                    else:
                        # Resize image
                        import cv2
                        import numpy as np
                        img_array = np.fromfile(str(input_file), dtype=np.uint8)
                        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                        if img is not None:
                            h, w = img.shape[:2]
                            if w > 800:
                                scale = 800 / w
                                img = cv2.resize(img, (0,0), fx=scale, fy=scale)
                            is_success, buffer = cv2.imencode(".jpg", img)
                            if is_success:
                                with open(thumb_path, "wb") as f:
                                    f.write(buffer)
                except Exception as e:
                    print(f"Thumbnail error: {e}")

                manifest_entry["thumbnail"] = thumb_filename

                if is_video:
                    # === FLUXO DE VÍDEO ===
                    out_fa = f"{prefix}_file_analysis.json"
                    out_cont = f"{prefix}_continuity.json"
                    out_struct = f"{prefix}_structure.json"
                    out_comp = f"{prefix}_compression.json"
                    out_quant = f"{prefix}_quantization.json"
                    out_prnu = f"{prefix}_prnu.json"
                    
                    # File Analysis
                    self.progress.emit(f"[{input_file.name}] Análise de Arquivo...")
                    FileAnalysisModule(cm).run(input_file, output_filename=out_fa)
                    manifest_entry["analysis_files"]["file_analysis"] = out_fa
                    
                    # Continuity
                    self.progress.emit(f"[{input_file.name}] Análise de Continuidade...")
                    ContinuityModule(cm).run(input_file, output_filename=out_cont)
                    manifest_entry["analysis_files"]["continuity_analysis"] = out_cont

                    # Structure Analysis (Atom Map)
                    self.progress.emit(f"[{input_file.name}] Mapeamento de Estrutura...")
                    StructureAnalysisModule(cm).run(input_file, output_filename=out_struct)
                    manifest_entry["analysis_files"]["structure_analysis"] = out_struct
                    
                    # Compression Analysis
                    self.progress.emit(f"[{input_file.name}] Análise Estatística...")
                    CompressionAnalysisModule(cm).run(input_file, output_filename=out_comp)
                    manifest_entry["analysis_files"]["compression_analysis"] = out_comp

                    # Quantization Analysis
                    self.progress.emit(f"[{input_file.name}] Análise de Quantização...")
                    QuantizationAnalysisModule(cm).run(input_file, output_filename=out_quant)
                    manifest_entry["analysis_files"]["quantization_analysis"] = out_quant
                    
                    # PRNU Analysis (Video)
                    self.progress.emit(f"[{input_file.name}] Análise de Fonte (PRNU)...")
                    prnu_mod = PrnuAnalysisModule(cm)
                    prnu_mod.frame_limit = int(self.config.get('prnu_frame_limit', 50))
                    prnu_res = prnu_mod.run(input_file, output_filename=out_prnu)
                    manifest_entry["analysis_files"]["prnu_analysis"] = out_prnu
                    
                    if prnu_res.get("status") == "extracted":
                        prnu_fingerprints.append({
                            "name": input_file.name,
                            "path": cm.results_dir / prnu_res["fingerprint_file"]
                        })

                    # Deepfake Analysis (Video)
                    self.progress.emit(f"[{input_file.name}] Análise de Deepfake em Vídeo (Jitter Temporal)...")
                    out_df = f"{prefix}_deepfake_analysis.json"
                    df_res = DeepfakeAnalysisModule(config=self.config).run_video(input_file)
                    
                    with open(cm.results_dir / out_df, 'w', encoding='utf-8') as f:
                        json.dump(df_res, f, indent=4)
                    manifest_entry["analysis_files"]["deepfake_analysis"] = out_df

                else:
                    # === FLUXO DE IMAGEM ===
                    out_img = f"{prefix}_image_analysis.json"
                    
                    self.progress.emit(f"[{input_file.name}] Análise Forense de Imagem (ELA + Meta + PRNU)...")
                    img_res = ImageForensicsModule(cm, config=self.config).run(input_file, output_filename=out_img, progress_callback=self.progress.emit)
                    manifest_entry["analysis_files"]["image_analysis"] = out_img
                    
                    # Deepfake Analysis
                    self.progress.emit(f"[{input_file.name}] Análise de Deepfake/Splicing (Face & Body)...")
                    out_df = f"{prefix}_deepfake_analysis.json"
                    df_res = DeepfakeAnalysisModule(config=self.config).run_image(input_file)
                    
                    # Salvar resultado deepfake
                    with open(cm.results_dir / out_df, 'w', encoding='utf-8') as f:
                        json.dump(df_res, f, indent=4)
                    manifest_entry["analysis_files"]["deepfake_analysis"] = out_df
                    
                    # Coletar Fingerprint do resultado da imagem
                    prnu_res = img_res.get("prnu_analysis", {})
                    if prnu_res.get("status") == "extracted":
                         prnu_fingerprints.append({
                            "name": input_file.name,
                            "path": cm.results_dir / prnu_res["fingerprint_file"]
                        })
                
                # Add to manifest list
                batch_manifest.append(manifest_entry)

            # Comparação PRNU All-to-All (Vídeos e Imagens)
            if len(prnu_fingerprints) > 1:
                self.progress.emit("Calculando Matriz de Similaridade PRNU (Multimídia)...")
                comparison_matrix = []
                
                for i in range(len(prnu_fingerprints)):
                    row = []
                    for j in range(len(prnu_fingerprints)):
                        if i == j:
                            row.append({"pce": -1, "match": True, "self": True}) 
                        else:
                            fp1 = prnu_fingerprints[i]
                            fp2 = prnu_fingerprints[j]
                            res = PrnuAnalysisModule.compare_fingerprints(fp1["path"], fp2["path"])
                            row.append(res)
                    comparison_matrix.append({
                        "source": prnu_fingerprints[i]["name"],
                        "results": row
                    })
                
                matrix_path = cm.results_dir / "prnu_matrix.json"
                with open(matrix_path, 'w', encoding='utf-8') as f:
                    json.dump({"matrix": comparison_matrix, "files": [x['name'] for x in prnu_fingerprints]}, f, indent=4)
            
            # Salvar Manifesto
            manifest_path = cm.results_dir / "batch_manifest.json"
            with open(manifest_path, 'w', encoding='utf-8') as mf:
                json.dump(batch_manifest, mf, indent=2, ensure_ascii=False)
            
            # Reporting
            self.progress.emit("Gerando Relatório Unificado (LaTeX)...")
            ReportingModule(cm).generate()
            
            self.progress.emit(f"Concluído! Relatório em: {cm.report_dir}")
            self.finished.emit(True, str(cm.report_dir))
            
        except Exception as e:
            self.progress.emit(f"ERRO: {str(e)}")
            import traceback
            traceback.print_exc()
            self.finished.emit(False, str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Análise Forense (Vídeo e Imagem) - Verificação de Edição")
        self.resize(800, 600)
        
        # Layout Principal
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Seleção de Arquivo
        file_layout = QHBoxLayout()
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("Selecione arquivos de vídeo ou imagem...")
        self.file_input.setReadOnly(True)
        self.browse_btn = QPushButton("Selecionar Arquivos")
        self.browse_btn.clicked.connect(self.browse_file)
        
        file_layout.addWidget(self.file_input)
        file_layout.addWidget(self.browse_btn)
        
        self.settings_btn = QPushButton("Configurações")
        self.settings_btn.clicked.connect(self.open_settings)
        file_layout.addWidget(self.settings_btn)
        
        layout.addLayout(file_layout)
        
        # Botão de Ação
        self.run_btn = QPushButton("Iniciar Análise Forense")
        self.run_btn.clicked.connect(self.start_analysis)
        self.run_btn.setEnabled(False)
        layout.addWidget(self.run_btn)
        
        # Log/Output
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        layout.addWidget(self.log_output)
        
        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)
        
        self.worker = None
        self.selected_files = [] 
    
    def browse_file(self):
        # Permite seleção múltipla
        filters = "Forensic Files (*.mp4 *.mkv *.avi *.mov *.jpg *.jpeg *.png *.tif *.tiff *.webp);;Videos (*.mp4 *.mkv *.avi *.mov);;Images (*.jpg *.jpeg *.png *.tif *.tiff *.webp)"
        fnames, _ = QFileDialog.getOpenFileNames(self, "Selecionar Arquivos", "", filters)
        if fnames:
            self.selected_files = [Path(f) for f in fnames]
            if len(self.selected_files) == 1:
                self.file_input.setText(str(self.selected_files[0]))
            else:
                self.file_input.setText(f"{len(self.selected_files)} arquivos selecionados")
            self.run_btn.setEnabled(True)

    def open_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec()
    
    def start_analysis(self):
        if not self.selected_files:
            QMessageBox.critical(self, "Erro", "Nenhum arquivo selecionado!")
            return
            
        # Solicitar diretório de saída
        output_dir = QFileDialog.getExistingDirectory(self, "Selecionar Pasta para Salvar Relatórios")
        if not output_dir:
            return  # Usuário cancelou
            
        # Sugerir nome padrão
        if len(self.selected_files) == 1:
            default_name = f"case_{self.selected_files[0].stem}"
        else:
            default_name = f"case_BATCH_{len(self.selected_files)}_FILES_{self.selected_files[0].stem}"
            
        # Perguntar nome da pasta ao usuário
        from PySide6.QtWidgets import QInputDialog
        case_name, ok = QInputDialog.getText(self, "Nome do Caso", 
                                           "Digite o nome da pasta a ser criada:", 
                                           text=default_name)
        if not ok or not case_name.strip():
            return # Cancelou ou vazio
            
        self.run_btn.setEnabled(False)
        self.browse_btn.setEnabled(False)
        self.settings_btn.setEnabled(False)
        self.progress_bar.setRange(0, 0) # Indeterminate
        self.log_output.clear()
        
        # Load Config
        config = DEFAULT_CONFIG.copy()
        if Path("config.json").exists():
            try:
                with open("config.json", 'r') as f:
                    config.update(json.load(f))
            except: pass
        
        # Passar case_name explicitamente para o Worker se possível, 
        # mas o worker atual gera o nome internamente. Precisamos mudar o Worker __init__ também.
        # Vamos passar o case_name para o Worker.
        self.worker = AnalysisWorker(self.selected_files, Path(output_dir), case_name=case_name, config=config)
        self.worker.progress.connect(self.update_log)
        self.worker.finished.connect(self.analysis_finished)
        self.worker.start()

    def update_log(self, message):
        self.log_output.append(message)

    def analysis_finished(self, success, result_path):
        self.run_btn.setEnabled(True)
        self.browse_btn.setEnabled(True)
        self.settings_btn.setEnabled(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        
        if success:
            QMessageBox.information(self, "Sucesso", f"Análise concluída!\n\nRelatórios salvos em:\n{result_path}")
        else:
            QMessageBox.critical(self, "Falha", f"Ocorreu um erro durante a análise:\n{result_path}")

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
