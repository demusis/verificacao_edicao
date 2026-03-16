import sys
from pathlib import Path
import os
import json
import socket
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                               QFileDialog, QTextEdit, QProgressBar, QMessageBox)
from PySide6.QtCore import Qt, QThread, Signal

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
from modules.audio_forensics import AudioForensicsModule  # AUDIO
from modules.audio_deepfake import AudioDeepfakeModule  # AUDIO
from app.settings_dialog import SettingsDialog, DEFAULT_CONFIG, load_config
try:
    from app.version import VERSION, BUILD_DATE
except ImportError:
    VERSION = "Dev"
    BUILD_DATE = "Unknown"

from modules.reporting import ReportingModule
import json

class AnalysisWorker(QThread):
    """Worker para executar a análise em background sem travar a GUI."""
    progress = Signal(str)
    progress_val = Signal(int)
    progress_max = Signal(int)
    finished = Signal(bool, str) # success, message
    
    def __init__(self, input_files: list[Path], output_dir: Path, case_name: str = None, config: dict = None):
        super().__init__()
        self.input_files = input_files
        self.output_dir = output_dir
        self.config = config or {}
        self.case_name = case_name
        self._is_cancelled = False
        
    def cancel(self):
        self._is_cancelled = True
        self.progress.emit("Cancelamento solicitado. Abortando processo assim que possível...")
        
    def _is_video(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.dav']
    
    def _is_audio(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in ['.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma', '.opus']
    
    def _has_video_stream(self, file_path: Path) -> bool:
        """Verifica se o arquivo realmente contém um stream de vídeo (não apenas áudio)."""
        import subprocess
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0", 
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(file_path)],
                capture_output=True, text=True, timeout=10
            )
            return "video" in result.stdout.lower()
        except Exception:
            # Em caso de erro, assume que tem vídeo se a extensão indicar
            return True

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
            self.progress_max.emit(len(self.input_files))
            
            # Setup com diretório personalizado
            cm = CaseManager(case_name, base_dir=self.output_dir)
            cm.setup()
            self.progress.emit(f"Diretório do caso: {cm.case_dir}")

            batch_manifest = []
            prnu_fingerprints = [] # List of tuples: (filename, npy_path)
            
            # --- LÓGICA DE RETOMADA DE PROCESSAMENTO ---
            manifest_path = cm.results_dir / "batch_manifest.json"
            processed_files = {}
            if getattr(self.config, 'resume_processing', True) and manifest_path.exists():
                self.progress.emit("Procurando processamento anterior para retomar...")
                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        existing_manifest = json.load(f)
                    for entry in existing_manifest:
                        fname = entry.get("filename")
                        if fname:
                            processed_files[fname] = entry
                            # Adicionar também pelo stem para redundância
                            processed_files[Path(fname).stem.lower()] = entry
                            
                    if processed_files:
                        self.progress.emit(f"✅ Retomada Ativa: Detectados {len(existing_manifest)} registros de arquivos já concluídos.")
                    else:
                        self.progress.emit("Nenhum arquivo processado anteriormente encontrado nesta pasta.")
                except Exception as e:
                    self.progress.emit(f"[AVISO] Falha ao carregar manifesto anterior: {e}")
            
            total_files = len(self.input_files)
            # Contagem robusta
            already_done_list = []
            for f in self.input_files:
                if f.name in processed_files or f.stem.lower() in processed_files:
                    already_done_list.append(f.name)
            
            already_done = len(already_done_list)
            remaining = total_files - already_done
            
            self.progress.emit(f"📊 Resumo do Lote: {total_files} total | {already_done} já feitos | {remaining} para processar.")
            self.progress.emit("-" * 40)

            for idx, input_file in enumerate(self.input_files):
                if self._is_cancelled:
                    self.progress.emit("ANÁLISE CANCELADA PELO USUÁRIO.")
                    self.finished.emit(False, "Cancelado")
                    return
                    
                self.progress_val.emit(idx)
                
                try:
                    # Verifica se deve pular (retomada de processamento)
                    found_entry = None
                    if input_file.name in processed_files:
                        found_entry = processed_files[input_file.name]
                    elif input_file.stem.lower() in processed_files:
                        found_entry = processed_files[input_file.stem.lower()]

                    if found_entry:
                        # Log de Pulo (Saltando)
                        self.progress.emit(f"[{idx+1}/{total_files}] SALTANDO (Concluído): {input_file.name}")
                        entry = found_entry
                        batch_manifest.append(entry)
                        
                        # Restaurar prnu cache para a matriz combinatória final
                        prnu_json_name = entry.get("analysis_files", {}).get("prnu_analysis")
                        if prnu_json_name:
                            prnu_path = cm.results_dir / prnu_json_name
                            if prnu_path.exists():
                                try:
                                    with open(prnu_path, 'r', encoding='utf-8') as f:
                                        prnu_data = json.load(f)
                                        if prnu_data.get("status") == "extracted" and "fingerprint_file" in prnu_data:
                                            prnu_fingerprints.append({
                                                "name": input_file.name,
                                                "path": cm.results_dir / prnu_data["fingerprint_file"]
                                            })
                                except Exception:
                                    pass
                        
                        # Verificar se precisa gerar o PDF individual pendente (gerado na extração via script)
                        if getattr(self.config, 'report_individual', False):
                            pdf_base_name = f"relatorio_{idx+1:02d}_{input_file.stem}"
                            pdf_ind_path = cm.report_dir / f"{pdf_base_name}.pdf"
                            if not pdf_ind_path.exists():
                                self.progress.emit(f"[{input_file.name}] Recuperando e gerando PDF pendente do processamento anterior...")
                                try:
                                    ReportingModule(cm, config=self.config).generate_individual(idx, entry)
                                except Exception as e:
                                    self.progress.emit(f"[{input_file.name}] Erro ao gerar PDF pendente: {e}")
                                    
                        continue
                        
                    # --- MECANISMO DE CLUSTER (LOCK) ---
                    # Evita que dois PCs processem o mesmo arquivo simultaneamente em rede local
                    lock_path = cm.results_dir / f"{idx+1:02d}_{input_file.stem}.lock"
                    if lock_path.exists():
                        try:
                            with open(lock_path, 'r', encoding='utf-8') as lf:
                                owner = lf.read().strip()
                            self.progress.emit(f"[{idx+1}/{total_files}] OCUPADO: {input_file.name} (Por {owner})")
                        except:
                            self.progress.emit(f"[{idx+1}/{total_files}] OCUPADO: {input_file.name} (Por outro PC)")
                        continue
                    
                    # Tentar travar o arquivo para este PC
                    try:
                        with open(lock_path, 'x', encoding='utf-8') as lf:
                            lf.write(socket.gethostname())
                    except FileExistsError:
                        self.progress.emit(f"[{idx+1}/{total_files}] CONFLITO EVITADO: Outro PC acabou de pegar este arquivo")
                        continue
                        
                    self.progress.emit(f"--- Processando Arquivo {idx+1}/{total_files}: {input_file.name} ---")
                    self._process_single_file(idx, input_file, batch_manifest, prnu_fingerprints, cm)
                    
                    # Salvar manifesto de forma distribuida (RELOAD + MERGE)
                    try:
                        import time, random
                        # Pequeno delay aleatório para reduzir colisões de escrita em rede SMB
                        time.sleep(random.uniform(0.1, 0.4))
                        
                        m_data = []
                        if manifest_path.exists():
                            with open(manifest_path, 'r', encoding='utf-8') as mf_read:
                                m_data = json.load(mf_read)
                        
                        # Pegar a última entrada gerada por este PC
                        new_entry = batch_manifest[-1]
                        
                        # Merge: Adicionar apenas se não estiver lá no disco
                        if not any(e.get('filename') == new_entry['filename'] for e in m_data):
                            m_data.append(new_entry)
                            
                            with open(manifest_path, 'w', encoding='utf-8') as mf_write:
                                json.dump(m_data, mf_write, indent=2, ensure_ascii=False)
                    except Exception as e:
                        self.progress.emit(f"AVISO: Falha ao sincronizar manifesto global: {e}")
                        
                    # Gerar Relatório Individual imediato (Gradual Release)
                    if getattr(self.config, 'report_individual', False):
                        self.progress.emit(f"[{input_file.name}] Gerando PDF de Relatório Individual...")
                        ReportingModule(cm, config=self.config).generate_individual(idx, batch_manifest[-1])

                except Exception as file_err:
                    self.progress.emit(f"ERRO CRÍTICO no arquivo {input_file.name}: {file_err}. Pulando para o próximo.")
                    import traceback
                    traceback.print_exc()
                    continue

            self.progress_val.emit(len(self.input_files))

            if self._is_cancelled:
                self.progress.emit("ANÁLISE CANCELADA (na fase de relatórios).")
                self.finished.emit(False, "Cancelado")
                return

            # Comparação PRNU All-to-All (Vídeos e Imagens)

            # Comparação PRNU All-to-All (Vídeos e Imagens)
            self.progress.emit(f"[DEBUG] Total de fingerprints PRNU coletados: {len(prnu_fingerprints)}")
            for fp in prnu_fingerprints:
                self.progress.emit(f"[DEBUG]   - {fp['name']}: {fp['path']}")
            
            if getattr(self.config, 'report_prnu', True) and len(prnu_fingerprints) > 1:
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
                self.progress.emit(f"[DEBUG] Matriz PRNU salva em: {matrix_path}")
            else:
                self.progress.emit(f"[DEBUG] Comparação PRNU pulada: apenas {len(prnu_fingerprints)} fingerprint(s) coletado(s). Precisa de pelo menos 2.")
            
            # Salvar Manifesto Final (Sincronizado para Cluster)
            manifest_path = cm.results_dir / "batch_manifest.json"
            final_data = []
            try:
                if manifest_path.exists():
                    with open(manifest_path, 'r', encoding='utf-8') as mf_read:
                        final_data = json.load(mf_read)
                
                # Merge com o que este nó produziu/pulou
                for e_mem in batch_manifest:
                    if not any(e_disk.get('filename') == e_mem['filename'] for e_disk in final_data):
                        final_data.append(e_mem)
                
                with open(manifest_path, 'w', encoding='utf-8') as mf_write:
                    json.dump(final_data, mf_write, indent=2, ensure_ascii=False)
            except:
                final_data = batch_manifest # Fallback

            # Reporting - Tenta gerar o consolidado FINAL se parecer que o lote acabou
            if len(final_data) >= total_files:
                self.progress.emit("Gerando Relatório Unificado de Finalização (Lote Completo)...")
                try:
                    ReportingModule(cm, config=self.config).generate()
                except Exception as rep_err:
                    self.progress.emit(f"Erro no Report Final: {rep_err}")
                self.progress.emit(f"Processamento concluído com sucesso! Relatórios em: {cm.report_dir}")
                self.finished.emit(True, str(cm.report_dir))
            else:
                self.progress.emit(f"Trabalho parcial deste nó concluído ({len(batch_manifest)}/{total_files}).")
                self.progress.emit("Aguardando finalização dos outros nós para o relatório consolidado.")
                self.finished.emit(True, "Parcial")
            
        except Exception as e:
            self.progress.emit(f"ERRO: {str(e)}")
            import traceback
            traceback.print_exc()
            self.finished.emit(False, str(e))
                
    def _process_single_file(self, idx: int, input_file, batch_manifest: list, prnu_fingerprints: list, cm):
            prefix = f"{idx+1:02d}_{input_file.stem}"
            
            # Detectar tipo de arquivo baseado em extensão E conteúdo real
            is_video_container = self._is_video(input_file)
            is_audio_file = self._is_audio(input_file)
            
            # Para containers de vídeo, verificar se realmente tem stream de vídeo
            has_video_stream = False
            if is_video_container:
                has_video_stream = self._has_video_stream(input_file)
            
            # Definir tipo correto para o manifesto
            if has_video_stream:
                file_type = "video"
            elif is_video_container or is_audio_file:
                file_type = "audio"
            else:
                file_type = "image"
            
            # DEBUG: Mostrar classificação do arquivo
            self.progress.emit(f"[DEBUG] Arquivo: {input_file.name} | is_video_container={is_video_container} | is_audio_file={is_audio_file} | has_video_stream={has_video_stream} | file_type={file_type}")
            
            manifest_entry = {
                "filename": input_file.name,
                "type": file_type,
                "analysis_files": {}
            }
            
            if has_video_stream:
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
                if has_video_stream:
                    # Extract first frame
                    import subprocess
                    subprocess.run([
                        "ffmpeg", "-y", "-i", str(input_file), 
                        "-vframes", "1", "-update", "1", "-q:v", "2", 
                        str(thumb_path)
                    ], check=False, capture_output=True)
                elif is_video_container or is_audio_file:
                    # Arquivo apenas-áudio - sem thumbnail
                    thumb_filename = None
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
                thumb_filename = None

            if thumb_filename:
                manifest_entry["thumbnail"] = thumb_filename

            if has_video_stream:
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

                manifest_entry["analysis_files"]["continuity_analysis"] = out_cont

                # Structure Analysis (Atom Map)
                if getattr(self.config, 'report_structure', True):
                    self.progress.emit(f"[{input_file.name}] Mapeamento de Estrutura...")
                    StructureAnalysisModule(cm).run(input_file, output_filename=out_struct)
                    manifest_entry["analysis_files"]["structure_analysis"] = out_struct
                
                # Compression Analysis
                if getattr(self.config, 'report_benford', True):
                    self.progress.emit(f"[{input_file.name}] Análise Estatística...")
                    CompressionAnalysisModule(cm).run(input_file, output_filename=out_comp)
                    manifest_entry["analysis_files"]["compression_analysis"] = out_comp

                # Quantization Analysis
                if getattr(self.config, 'report_quantization', True):
                    self.progress.emit(f"[{input_file.name}] Análise de Quantização...")
                    QuantizationAnalysisModule(cm).run(input_file, output_filename=out_quant)
                    manifest_entry["analysis_files"]["quantization_analysis"] = out_quant
                
                # PRNU Analysis (Video)
                if getattr(self.config, 'report_prnu', True):
                    self.progress.emit(f"[{input_file.name}] Análise de Fonte (PRNU)...")
                    prnu_mod = PrnuAnalysisModule(cm)
                    prnu_mod.frame_limit = self.config.prnu_frame_limit
                    prnu_res = prnu_mod.run(input_file, output_filename=out_prnu)
                    manifest_entry["analysis_files"]["prnu_analysis"] = out_prnu
                    
                    if prnu_res.get("status") == "extracted":
                        prnu_fingerprints.append({
                            "name": input_file.name,
                            "path": cm.results_dir / prnu_res["fingerprint_file"]
                        })
                        self.progress.emit(f"[DEBUG] PRNU Video coletado: {input_file.name} (total: {len(prnu_fingerprints)})")
                    else:
                        self.progress.emit(f"[DEBUG] PRNU Video NÃO extraído: {input_file.name} - status: {prnu_res.get('status')}")

                # Deepfake Analysis (Video)
                if getattr(self.config, 'report_deepfake', True):
                    self.progress.emit(f"[{input_file.name}] Análise de Deepfake em Vídeo (Jitter Temporal)...")
                    out_df = f"{prefix}_deepfake_analysis.json"
                    df_res = DeepfakeAnalysisModule(config=self.config).run_video(input_file)
                    
                    with open(cm.results_dir / out_df, 'w', encoding='utf-8') as f:
                        json.dump(df_res, f, indent=4)
                    manifest_entry["analysis_files"]["deepfake_analysis"] = out_df

            elif file_type == "image":
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
                     self.progress.emit(f"[DEBUG] PRNU Imagem coletado: {input_file.name} (total: {len(prnu_fingerprints)})")
                else:
                     self.progress.emit(f"[DEBUG] PRNU Imagem NÃO extraído: {input_file.name} - status: {prnu_res.get('status')}")
            
            # === FLUXO DE ÁUDIO ===
            # Análise de áudio: para arquivos de áudio puro OU para extrair faixa de áudio de vídeos/containers
            if is_audio_file or is_video_container:
                out_audio = f"{prefix}_audio_analysis.json"
                out_audio_df = f"{prefix}_audio_deepfake.json"
                
                # Análise Forense de Áudio
                # Envolto em try/except para não interromper a comparação PRNU se falhar
                try:
                    if getattr(self.config, 'report_audio_metadata', True):
                        self.progress.emit(f"[{input_file.name}] Análise Forense de Áudio...")
                        audio_res = AudioForensicsModule(cm, config=self.config).run(
                            input_file, output_filename=out_audio, progress_callback=self.progress.emit
                        )
                        manifest_entry["analysis_files"]["audio_analysis"] = out_audio
                except Exception as audio_err:
                    self.progress.emit(f"[{input_file.name}] AVISO: Falha na análise de áudio: {audio_err}")
                    print(f"Audio analysis error: {audio_err}")
                
                # Deepfake de Voz
                try:
                    if getattr(self.config, 'report_audio_deepfake', True):
                        self.progress.emit(f"[{input_file.name}] Detecção de Deepfake de Voz...")
                        audio_df_res = AudioDeepfakeModule(cm, config=self.config).run(
                            input_file, output_filename=out_audio_df, progress_callback=self.progress.emit
                        )
                        manifest_entry["analysis_files"]["audio_deepfake"] = out_audio_df
                except Exception as audio_df_err:
                    self.progress.emit(f"[{input_file.name}] AVISO: Falha na detecção de deepfake de voz: {audio_df_err}")
                    print(f"Audio deepfake error: {audio_df_err}")
            
            # Add to manifest list
            batch_manifest.append(manifest_entry)

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
        
        self.browse_folder_btn = QPushButton("Abrir Pasta (Mídia/Forense)")
        self.browse_folder_btn.clicked.connect(self.browse_folder)
        
        file_layout.addWidget(self.file_input)
        file_layout.addWidget(self.browse_btn)
        file_layout.addWidget(self.browse_folder_btn)
        
        self.settings_btn = QPushButton("Configurações")
        self.settings_btn.clicked.connect(self.open_settings)
        file_layout.addWidget(self.settings_btn)

        self.about_btn = QPushButton("Sobre")
        self.about_btn.clicked.connect(self.show_about)
        file_layout.addWidget(self.about_btn)
        
        layout.addLayout(file_layout)
        
        # Botões de Ação Dinâmicos
        action_layout = QHBoxLayout()
        self.run_btn = QPushButton("Iniciar Análise Forense")
        self.run_btn.clicked.connect(self.start_analysis)
        self.run_btn.setEnabled(False)
        
        self.cancel_btn = QPushButton("Cancelar Análise")
        self.cancel_btn.clicked.connect(self.cancel_analysis)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setStyleSheet("background-color: #E74C3C; color: white;")
        
        action_layout.addWidget(self.run_btn)
        action_layout.addWidget(self.cancel_btn)
        layout.addLayout(action_layout)
        
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
        filters = "Forensic Files (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.dav *.jpg *.jpeg *.png *.tif *.tiff *.webp *.mp3 *.wav *.flac *.ogg *.m4a *.aac *.opus *.wma);;Videos (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.dav);;Images (*.jpg *.jpeg *.png *.tif *.tiff *.webp);;Audio (*.mp3 *.wav *.flac *.ogg *.m4a *.aac *.opus *.wma)"
        fnames, _ = QFileDialog.getOpenFileNames(self, "Selecionar Arquivos", "", filters)
        if fnames:
            self.selected_files = [Path(f) for f in fnames]
            if len(self.selected_files) == 1:
                self.file_input.setText(str(self.selected_files[0]))
            else:
                self.file_input.setText(f"{len(self.selected_files)} arquivos selecionados")
            self.run_btn.setEnabled(True)

    def browse_folder(self):
        """Abre seletor de pasta e busca recursivamente todos os arquivos suportados."""
        MEDIA_EXTENSIONS = {
            # Videos
            '.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.dav',
            # Images
            '.jpg', '.jpeg', '.png', '.tif', '.tiff', '.webp',
            # Audio
            '.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.opus', '.wma'
        }
        
        folder = QFileDialog.getExistingDirectory(self, "Selecionar Pasta com Arquivos Forenses")
        if not folder:
            return
        
        folder_path = Path(folder)
        
        # Busca recursiva por arquivos multimídia
        media_files = []
        for ext in MEDIA_EXTENSIONS:
            media_files.extend(folder_path.rglob(f'*{ext}'))
            media_files.extend(folder_path.rglob(f'*{ext.upper()}'))
        
        # Remover duplicatas (caso ext e EXT capturem o mesmo arquivo) e ordenar
        media_files = sorted(set(media_files))
        
        if not media_files:
            QMessageBox.warning(
                self, "Nenhum arquivo encontrado",
                f"Nenhum arquivo multimídia foi encontrado em:\n{folder}\n\n"
                f"Extensões procuradas: {', '.join(sorted(MEDIA_EXTENSIONS))}"
            )
            return
        
        self.selected_files = media_files
        self.file_input.setText(f"{len(media_files)} arquivos encontrados em: {folder_path.name}")
        self.run_btn.setEnabled(True)
        
        # Mostrar lista de arquivos encontrados no log
        self.log_output.clear()
        self.log_output.append(f"📂 Pasta selecionada: {folder}")
        self.log_output.append(f"🎬 {len(media_files)} arquivo(s) de mídia encontrado(s):\n")
        for vf in media_files:
            # Mostrar caminho relativo à pasta selecionada
            try:
                rel = vf.relative_to(folder_path)
            except ValueError:
                rel = vf.name
            self.log_output.append(f"  • {rel}")
        self.log_output.append("\n✅ Pronto para iniciar análise.")

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
        self.cancel_btn.setEnabled(True)
        self.browse_btn.setEnabled(False)
        self.browse_folder_btn.setEnabled(False)
        self.settings_btn.setEnabled(False)
        self.progress_bar.setRange(0, 0) # Indeterminate at first
        self.log_output.clear()
        
        # Load Config
        config = load_config()
        
        # Passar case_name explicitamente para o Worker se possível, 
        # mas o worker atual gera o nome internamente. Precisamos mudar o Worker __init__ também.
        # Vamos passar o case_name para o Worker.
        self.worker = AnalysisWorker(self.selected_files, Path(output_dir), case_name=case_name, config=config)
        self.worker.progress.connect(self.update_log)
        self.worker.progress_max.connect(self.progress_bar.setMaximum)
        self.worker.progress_val.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self.analysis_finished)
        self.worker.start()

    def cancel_analysis(self):
        if self.worker and self.worker.isRunning():
            self.cancel_btn.setEnabled(False)
            self.cancel_btn.setText("Cancelando...")
            self.worker.cancel()

    def update_log(self, message):
        self.log_output.append(message)

    def show_about(self):
        QMessageBox.about(self, "Sobre o VerificacaoEdicao",
            f"""<h3>VerificacaoEdicao</h3>
            <p>Ferramenta de Análise Forense de Multimídia.</p>
            <p><b>Versão:</b> {VERSION}</p>
            <p><b>Data do Build:</b> {BUILD_DATE}</p>
            <p>Desenvolvido para verificação de autenticidade e detecção de edições.</p>
            <p><b>Gerência de perícias em Áudio e Vídeo (GPAV)</b><br>
            Perícia Oficial e Identificação Técnica do Estado de Mato Grosso (POLITEC/MT)</p>
            """
        )

    def analysis_finished(self, success, result_path):
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("Cancelar Análise")
        self.browse_btn.setEnabled(True)
        self.browse_folder_btn.setEnabled(True)
        self.settings_btn.setEnabled(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        
        if success:
            QMessageBox.information(self, "Sucesso", f"Análise concluída!\n\nRelatórios salvos em:\n{result_path}")
        else:
            QMessageBox.critical(self, "Falha", f"Ocorreu um erro durante a análise:\n{result_path}")

def main():
    # Garantir que o config.json exista com os padrões antes de iniciar
    load_config()
    
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
