import contextlib
import json
import os
import socket
import sys
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# Permitir execução direta sem -m
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Importações do Core e Modules
from app.cluster_dashboard import ClusterDashboard
from app.settings_dialog import SettingsDialog, load_config
from core.case_manager import CaseManager
from core.config_schema import AnalysisConfig
from core.subprocess_utils import run_command
from modules.audio_deepfake import AudioDeepfakeModule  # AUDIO
from modules.audio_forensics import AudioForensicsModule  # AUDIO
from modules.compression_analysis import CompressionAnalysisModule
from modules.continuity import ContinuityModule
from modules.deepfake_analysis import DeepfakeAnalysisModule  # NEW
from modules.file_analysis import FileAnalysisModule
from modules.image_forensics import ImageForensicsModule  # NEW
from modules.prnu_analysis import PrnuAnalysisModule
from modules.quantization_analysis import QuantizationAnalysisModule
from modules.structure_analysis import StructureAnalysisModule

try:
    from app.version import BUILD_DATE, VERSION
except ImportError:
    VERSION = "Dev"
    BUILD_DATE = "Unknown"

import threading

from modules.reporting import ReportingModule


class HeartbeatThread(threading.Thread):
    """Segmento que atualiza o arquivo de registro do nó em segundo plano."""
    def __init__(self, node_info_path, node_registration):
        super().__init__(daemon=True)
        self.node_info_path = node_info_path
        self.node_registration = node_registration
        self.stop_event = threading.Event()

    def run(self):
        from datetime import datetime
        while not self.stop_event.is_set():
            try:
                # Atualizar timestamp do coração
                self.node_registration["last_heartbeat"] = datetime.now().isoformat()
                with open(self.node_info_path, 'w', encoding='utf-8') as nf:
                    json.dump(self.node_registration, nf, indent=2, ensure_ascii=False)
            except Exception:
                pass
            # Espera 30 segundos, mas acorda se o evento for sinalizado (parada)
            self.stop_event.wait(30)

    def stop(self):
        self.stop_event.set()

class AnalysisWorker(QThread):
    """Worker para executar a análise em background sem travar a GUI."""
    progress = Signal(str)
    progress_val = Signal(int)
    progress_max = Signal(int)
    finished = Signal(bool, str) # success, message
    
    def __init__(self, input_files: list[Path], output_dir: Path,
                 case_name: str | None = None, config: AnalysisConfig | None = None):
        super().__init__()
        self.input_files = input_files
        self.output_dir = output_dir
        # AnalysisConfig é obrigatório: o código acessa atributos (ex: prnu_frame_limit)
        self.config = config or AnalysisConfig()
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
        try:
            result = run_command(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(file_path)],
                timeout=10
            )
            if result.returncode != 0:
                # Se ffprobe der erro (ex: nome de arquivo com caracteres estranhos),
                # assume fallback para True (é um vídeo baseado na extensão)
                return True
            return "video" in result.stdout.lower()
        except Exception:
            # Em caso de erro, assume que tem vídeo se a extensão indicar
            return True
    @staticmethod
    def _is_network_error(error: Exception) -> bool:
        """Verifica se um erro é relacionado a problemas de rede/acesso a arquivos."""
        network_indicators = (
            OSError, PermissionError, FileNotFoundError,
            ConnectionError, TimeoutError, IOError
        )
        if isinstance(error, network_indicators):
            return True
        # Verificar mensagens comuns de erro de rede no Windows
        err_msg = str(error).lower()
        network_keywords = [
            "network", "rede", "acesso", "access denied",
            "o caminho da rede", "the network path",
            "não é possível acessar", "cannot access",
            "sem espaço", "no space", "busy", "ocupado",
            "connection", "conexão", "winerror",
        ]
        return any(kw in err_msg for kw in network_keywords)

    def _wait_for_reconnect(self, test_path: Path, context: str = "") -> bool:
        """Aguarda até que o caminho de rede fique acessível novamente.
        
        Args:
            test_path: Diretório a testar (ex: results_dir)
            context: Descrição do que estava fazendo quando caiu
            
        Returns:
            True se reconectou com sucesso, False se excedeu max_attempts.
        """
        import time
        retry_interval = getattr(self.config, 'retry_interval_seconds', 60)
        max_attempts = getattr(self.config, 'retry_max_attempts', 10)
        
        for attempt in range(1, max_attempts + 1):
            if self._is_cancelled:
                return False
                
            self.progress.emit(
                f"⏸️ CONEXÃO PERDIDA{f' ({context})' if context else ''}. "
                f"Tentativa {attempt}/{max_attempts} em {retry_interval}s..."
            )
            
            # Esperar em blocos de 1 segundo para poder cancelar rapidamente
            for _ in range(retry_interval):
                if self._is_cancelled:
                    return False
                time.sleep(1)
            
            # Testar acesso ao diretório
            try:
                test_path.exists()
                # Tentar ler o diretório para ter certeza
                list(test_path.iterdir())
                self.progress.emit(
                    f"✅ CONEXÃO RESTABELECIDA após {attempt} tentativa(s)! Retomando processamento..."
                )
                return True
            except Exception as e:
                self.progress.emit(
                    f"❌ Tentativa {attempt}/{max_attempts} falhou: {e}"
                )
        
        self.progress.emit(
            f"🛑 DESISTINDO após {max_attempts} tentativas ({max_attempts * retry_interval}s). "
            "Verifique a conexão de rede."
        )
        return False

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
            # Sanitizar: Windows não aceita nomes de diretório com espaço/ponto no final
            case_name = case_name.strip().rstrip('. ')
                
            self.progress.emit(f"Iniciando caso: {case_name}")
            self.progress_max.emit(len(self.input_files))
            
            # Setup com diretório personalizado
            cm = CaseManager(case_name, base_dir=self.output_dir)
            cm.setup()
            self.progress.emit(f"Diretório do caso: {cm.case_dir}")

            batch_manifest = []
            prnu_fingerprints = [] # List of tuples: (filename, npy_path)

            # --- REGISTRO DO NÓ NO CLUSTER ---
            # Cria um JSON na pasta results/ com a lista completa de arquivos do lote.
            # Permite ao Dashboard saber o total de arquivos automaticamente.
            my_host = socket.gethostname()
            my_pid = os.getpid()
            node_info_path = cm.results_dir / f"_node_{my_host}_{my_pid}.json"
            node_registration = {}
            hb_thread = None
            try:
                from datetime import datetime
                node_registration = {
                    "hostname": my_host,
                    "pid": my_pid,
                    "total_files": len(self.input_files),
                    "files": [f.name for f in self.input_files],
                    "started_at": datetime.now().isoformat()
                }
                with open(node_info_path, 'w', encoding='utf-8') as nf:
                    json.dump(node_registration, nf, indent=2, ensure_ascii=False)
                self.progress.emit(f"📋 Nó registrado: {my_host}:{my_pid} ({len(self.input_files)} arquivos)")
            except Exception as e:
                self.progress.emit(f"[AVISO] Falha ao registrar nó no cluster: {e}")
                node_registration = {}
                node_info_path = None

            # Iniciar thread do Heartbeat (frequência regular em background)
            hb_thread = None
            if node_info_path and node_registration:
                hb_thread = HeartbeatThread(node_info_path, node_registration)
                hb_thread.start()
            
            # --- LÓGICA DE RETOMADA DE PROCESSAMENTO ---
            manifest_path = cm.results_dir / "batch_manifest.json"
            processed_files = {}
            if getattr(self.config, 'resume_processing', True) and manifest_path.exists():
                self.progress.emit("Procurando processamento anterior para retomar...")
                try:
                    with open(manifest_path, encoding='utf-8') as f:
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
                                    with open(prnu_path, encoding='utf-8') as f:
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
                                    # Registrar no manifesto que agora existe um PDF
                                    if pdf_ind_path.exists():
                                        # Split the dict update to help some static analysis tools avoid 'Never' types
                                        if "analysis_files" not in entry:
                                            entry["analysis_files"] = {}
                                        meta_files = entry["analysis_files"]
                                        if isinstance(meta_files, dict):
                                            meta_files["report_pdf"] = f"{pdf_base_name}.pdf"
                                except Exception as e:
                                    self.progress.emit(f"[{input_file.name}] Erro ao gerar PDF pendente: {e}")
                                    
                        continue
                        
                    # --- MECANISMO DE CLUSTER (LOCK) ---
                    # Evita que dois PCs processem o mesmo arquivo simultaneamente em rede local
                    lock_path = cm.results_dir / f"{idx+1:02d}_{input_file.stem}.lock"
                    if lock_path.exists():
                        try:
                            with open(lock_path, encoding='utf-8') as lf:
                                lock_content = lf.read().strip()
                            
                            my_host = socket.gethostname()
                            my_pid = os.getpid()
                            current_id = f"{my_host}:{my_pid}"
                            
                            if lock_content == current_id:
                                # Retomada de um crash dentro desta mesma sessão (incomum mas possível)
                                self.progress.emit(f"[{idx+1}/{total_files}] RE-ASSUMINDO LOCK: {input_file.name}")
                            elif ":" in lock_content:
                                host, pid = lock_content.split(":", 1)
                                if host == my_host:
                                    # É deste PC. Verificar se o processo ainda existe
                                    is_running = False
                                    try:
                                        import psutil
                                        is_running = psutil.pid_exists(int(pid))
                                    except Exception:
                                        # Fallback se não tiver psutil: assume que se o host é igual mas o PID é diferente, é outra instância rodando
                                        is_running = True 
                                    
                                    if is_running:
                                        self.progress.emit(f"[{idx+1}/{total_files}] OCUPADO (Instância {pid}): {input_file.name}")
                                        continue
                                    else:
                                        self.progress.emit(f"[{idx+1}/{total_files}] RECLAMANDO LOCK (Sessão {pid} caiu): {input_file.name}")
                                else:
                                    self.progress.emit(f"[{idx+1}/{total_files}] OCUPADO (PC {host}): {input_file.name}")
                                    continue
                            else:
                                # Formato antigo (apenas host)
                                if lock_content == my_host:
                                     self.progress.emit(f"[{idx+1}/{total_files}] RECLAMANDO LOCK (Formato antigo): {input_file.name}")
                                else:
                                    self.progress.emit(f"[{idx+1}/{total_files}] OCUPADO (PC {lock_content}): {input_file.name}")
                                    continue
                        except Exception:
                            self.progress.emit(f"[{idx+1}/{total_files}] LOCK INVÁLIDO detectado. Tentando assumir...")
                    
                    # Tentar travar o arquivo para esta instância específica
                    try:
                        my_id = f"{socket.gethostname()}:{os.getpid()}"
                        with open(lock_path, 'w', encoding='utf-8') as lf:
                            lf.write(my_id)
                    except Exception as e:
                        self.progress.emit(f"[{idx+1}/{total_files}] FALHA AO CRIAR LOCK: {e}")
                        continue
                        
                    try:
                        self.progress.emit(f"--- Processando Arquivo {idx+1}/{total_files}: {input_file.name} ---")

                        # Heartbeat (via dict compartilhado): atualizar _node_*.json com arquivo atual
                        try:
                            from datetime import datetime as _dt
                            node_registration["last_heartbeat"] = _dt.now().isoformat()
                            node_registration["current_file"] = input_file.name
                            node_registration["current_index"] = idx + 1
                            # A thread de background escreverá isso em breve, mas forçamos uma agora
                            if node_info_path:
                                with open(node_info_path, 'w', encoding='utf-8') as nf:
                                    json.dump(node_registration, nf, indent=2, ensure_ascii=False)
                        except Exception:
                            pass
                        # --- CÓPIA LOCAL TEMPORÁRIA (otimização de I/O) ---
                        local_copy_path = None
                        processing_file = input_file  # Arquivo a ser processado (original ou cópia local)
                        
                        if getattr(self.config, 'local_copy_enabled', False):
                            import shutil
                            import tempfile
                            
                            local_dir = getattr(self.config, 'local_copy_dir', '') or ''
                            if local_dir:
                                local_base = Path(local_dir)
                            else:
                                local_base = Path(tempfile.gettempdir())
                            
                            # Criar subdiretório para evitar conflitos
                            local_work_dir = local_base / "forensic_temp"
                            local_work_dir.mkdir(parents=True, exist_ok=True)
                            local_copy_path = local_work_dir / input_file.name
                            
                            try:
                                file_size_mb = input_file.stat().st_size / (1024 * 1024)
                                self.progress.emit(
                                    f"📋 Copiando para disco local ({file_size_mb:.1f} MB): {input_file.name}"
                                )
                                shutil.copy2(str(input_file), str(local_copy_path))
                                processing_file = local_copy_path
                                self.progress.emit(f"  └─ Cópia local concluída: {local_copy_path}")
                            except Exception as copy_err:
                                self.progress.emit(
                                    f"⚠️ Falha ao copiar localmente ({copy_err}). Usando arquivo de rede."
                                )
                                local_copy_path = None
                                processing_file = input_file
                        
                        try:
                            self._process_single_file(idx, processing_file, batch_manifest, prnu_fingerprints, cm)
                        finally:
                            # Limpar cópia local após uso (sucesso ou erro)
                            if local_copy_path and local_copy_path.exists():
                                try:
                                    local_copy_path.unlink()
                                    self.progress.emit(f"🗑️ Cópia local removida: {local_copy_path.name}")
                                except Exception:
                                    pass
                        
                        # Salvar manifesto de forma distribuida (RELOAD + MERGE)
                        try:
                            import random
                            import time
                            # Pequeno delay aleatório para reduzir colisões de escrita em rede SMB
                            time.sleep(random.uniform(0.1, 0.4))
                            
                            m_data = []
                            if manifest_path.exists():
                                with open(manifest_path, encoding='utf-8') as mf_read:
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
                            
                        # Heartbeat (via dict compartilhado): atualizar _node_*.json após término do arquivo
                        try:
                            from datetime import datetime as _dt
                            now_iso = _dt.now().isoformat()
                            node_registration.update({
                                "last_heartbeat": now_iso,
                                "current_file": None,
                                "files_done": len([e for e in batch_manifest if e.get("filename")])
                            })
                            # Thread enviará a atualização se node_registration for compartilhado corretamente
                        except Exception:
                            pass
                    finally:
                        # SEMPRE remover o lock ao terminar ou se der erro
                        if lock_path.exists():
                            with contextlib.suppress(Exception):
                                lock_path.unlink()

                except Exception as file_err:
                    if self._is_network_error(file_err):
                        self.progress.emit(
                            f"⚠️ ERRO DE REDE ao processar {input_file.name}: {file_err}"
                        )
                        reconnected = self._wait_for_reconnect(
                            cm.results_dir,
                            context=f"processando {input_file.name}"
                        )
                        if reconnected:
                            # Reconectou: re-tentar este mesmo arquivo
                            # Remover lock anterior se existir (pode estar corrompido)
                            try:
                                if lock_path.exists():
                                    lock_path.unlink()
                            except Exception:
                                pass
                            # Remover entrada do manifest se foi adicionada parcialmente
                            if batch_manifest and batch_manifest[-1].get("filename") == input_file.name:
                                batch_manifest.pop()
                            # Re-inserir o arquivo na fila (decrementar idx para repetir)
                            self.progress.emit(f"🔄 Retentando arquivo: {input_file.name}")
                            # Como não podemos voltar no loop, adicionamos à lista
                            self.input_files.append(input_file)
                            total_files = len(self.input_files)
                            continue
                        else:
                            # Não reconectou: abortar processamento
                            self.progress.emit("🛑 Processamento ABORTADO por perda de conexão.")
                            self.finished.emit(False, "Conexão perdida")
                            return
                    else:
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
                    with open(manifest_path, encoding='utf-8') as mf_read:
                        final_data = json.load(mf_read)
                
                # Merge com o que este nó produziu/pulou
                for e_mem in batch_manifest:
                    if not any(e_disk.get('filename') == e_mem['filename'] for e_disk in final_data):
                        final_data.append(e_mem)
                
                with open(manifest_path, 'w', encoding='utf-8') as mf_write:
                    json.dump(final_data, mf_write, indent=2, ensure_ascii=False)
            except Exception as merge_err:
                self.progress.emit(f"AVISO: Falha ao consolidar manifesto final: {merge_err}")
                final_data = batch_manifest # Fallback

            # Reporting - Tenta gerar o consolidado FINAL se parecer que o lote acabou
            if len(final_data) >= total_files:
                self.progress.emit("Gerando Relatório Unificado de Finalização (Lote Completo)...")
                try:
                    ReportingModule(cm, config=self.config).generate()
                except Exception as rep_err:
                    self.progress.emit(f"Erro no Report Final: {rep_err}")
                self.progress.emit(f"Processamento concluído com sucesso! Relatórios em: {cm.report_dir}")
                # Limpar registro do nó (processamento bem-sucedido)
                if hb_thread:
                    hb_thread.stop()
                    hb_thread.join(timeout=2)
                try:
                    if node_info_path and node_info_path.exists():
                        node_info_path.unlink()
                except Exception:
                    pass
                self.finished.emit(True, str(cm.report_dir))
            else:
                self.progress.emit(f"Trabalho parcial deste nó concluído ({len(batch_manifest)}/{total_files}).")
                self.progress.emit("Aguardando finalização dos outros nós para o relatório consolidado.")
                # Limpar registro do nó (trabalho parcial concluído)
                if hb_thread:
                    hb_thread.stop()
                    hb_thread.join(timeout=2)
                try:
                    if node_info_path and node_info_path.exists():
                        node_info_path.unlink()
                except Exception:
                    pass
                self.finished.emit(True, "Parcial")
            
        except Exception as e:
            if 'hb_thread' in locals() and hb_thread:
                hb_thread.stop()
                hb_thread.join(timeout=2)
            try:
                if 'node_info_path' in locals() and node_info_path and node_info_path.exists():
                    node_info_path.unlink()
            except Exception:
                pass
            self.progress.emit(f"ERRO: {e!s}")
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
            
            # === THUMBNAIL GENERATION ===
            thumb_filename = f"thumb_{input_file.stem}.jpg"
            thumb_path = cm.results_dir / thumb_filename
            
            try:
                if has_video_stream:
                    # Extract first frame
                    run_command([
                        "ffmpeg", "-y", "-i", str(input_file),
                        "-vframes", "1", "-update", "1", "-q:v", "2",
                        str(thumb_path)
                    ], timeout=120)
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
                        w = img.shape[1]
                        if w > 800:
                            scale = 800 / w
                            img = cv2.resize(img, (0,0), fx=scale, fy=scale)
                        is_success, buffer = cv2.imencode(".jpg", img)
                        if is_success:
                            with open(thumb_path, "wb") as f:
                                f.write(buffer)
            except Exception as e:
                self.progress.emit(f"[{input_file.name}] AVISO: Falha ao gerar thumbnail: {e}")
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
                if not (cm.results_dir / out_fa).exists():
                    FileAnalysisModule(cm).run(input_file, output_filename=out_fa)
                else:
                    self.progress.emit("  └─ RECUPERADO (Arquivo já processado)")
                manifest_entry["analysis_files"]["file_analysis"] = out_fa
                
                # Continuity
                self.progress.emit(f"[{input_file.name}] Análise de Continuidade...")
                if not (cm.results_dir / out_cont).exists():
                    ContinuityModule(cm).run(input_file, output_filename=out_cont)
                else:
                    self.progress.emit("  └─ RECUPERADO (Arquivo já processado)")
                manifest_entry["analysis_files"]["continuity_analysis"] = out_cont

                # Structure Analysis (Atom Map)
                if getattr(self.config, 'report_structure', True):
                    self.progress.emit(f"[{input_file.name}] Mapeamento de Estrutura...")
                    if not (cm.results_dir / out_struct).exists():
                        StructureAnalysisModule(cm).run(input_file, output_filename=out_struct)
                    else:
                        self.progress.emit("  └─ RECUPERADO (Arquivo já processado)")
                    manifest_entry["analysis_files"]["structure_analysis"] = out_struct
                
                # Compression Analysis
                if getattr(self.config, 'report_benford', True):
                    self.progress.emit(f"[{input_file.name}] Análise Estatística...")
                    if not (cm.results_dir / out_comp).exists():
                        CompressionAnalysisModule(cm).run(input_file, output_filename=out_comp)
                    else:
                        self.progress.emit("  └─ RECUPERADO (Arquivo já processado)")
                    manifest_entry["analysis_files"]["compression_analysis"] = out_comp

                # Quantization Analysis
                if getattr(self.config, 'report_quantization', True):
                    self.progress.emit(f"[{input_file.name}] Análise de Quantização...")
                    if not (cm.results_dir / out_quant).exists():
                        QuantizationAnalysisModule(cm).run(input_file, output_filename=out_quant)
                    else:
                        self.progress.emit("  └─ RECUPERADO (Arquivo já processado)")
                    manifest_entry["analysis_files"]["quantization_analysis"] = out_quant
                
                # PRNU Analysis (Video)
                if getattr(self.config, 'report_prnu', True):
                    # For PRNU, we need the result data even if we skip run()
                    self.progress.emit(f"[{input_file.name}] Análise de Fonte (PRNU)...")
                    prnu_mod = PrnuAnalysisModule(cm)
                    
                    if not (cm.results_dir / out_prnu).exists():
                        prnu_mod.frame_limit = self.config.prnu_frame_limit
                        prnu_res = prnu_mod.run(input_file, output_filename=out_prnu)
                    else:
                        self.progress.emit("  └─ RECUPERADO (Arquivo já processado)")
                        try:
                            with open(cm.results_dir / out_prnu, encoding='utf-8') as f:
                                prnu_res = json.load(f)
                        except Exception:
                            prnu_res = {"status": "error"}

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
                        if not (cm.results_dir / out_audio).exists():
                            AudioForensicsModule(cm, config=self.config).run(
                                input_file, output_filename=out_audio, progress_callback=self.progress.emit
                            )
                        else:
                            self.progress.emit("  └─ RECUPERADO (Áudio analisado)")
                        manifest_entry["analysis_files"]["audio_analysis"] = out_audio
                except Exception as audio_err:
                    self.progress.emit(f"[{input_file.name}] AVISO: Falha na análise de áudio: {audio_err}")
                
                # Deepfake de Voz
                try:
                    if getattr(self.config, 'report_audio_deepfake', True):
                        self.progress.emit(f"[{input_file.name}] Detecção de Deepfake de Voz...")
                        if not (cm.results_dir / out_audio_df).exists():
                            AudioDeepfakeModule(cm, config=self.config).run(
                                input_file, output_filename=out_audio_df, progress_callback=self.progress.emit
                            )
                        else:
                            self.progress.emit("  └─ RECUPERADO (Deepfake de voz analisado)")
                        manifest_entry["analysis_files"]["audio_deepfake"] = out_audio_df
                except Exception as audio_df_err:
                    self.progress.emit(f"[{input_file.name}] AVISO: Falha na detecção de deepfake de voz: {audio_df_err}")
            
            # === FASE FINAL: GERAÇÃO DE PDF INDIVIDUAL ===
            # Tratada como uma fase de processamento que pode ser pulada se o arquivo existir.
            if getattr(self.config, 'report_individual', False):
                pdf_base_name = f"relatorio_{idx+1:02d}_{input_file.stem}"
                pdf_path = cm.report_dir / f"{pdf_base_name}.pdf"
                
                self.progress.emit(f"[{input_file.name}] Fase de Relatório Individual...")
                if not pdf_path.exists():
                    try:
                        from modules.reporting import ReportingModule
                        ReportingModule(cm, config=self.config).generate_individual(idx, manifest_entry)
                        self.progress.emit("  └─ Relatório PDF gerado com sucesso")
                    except Exception as pdf_err:
                        self.progress.emit(f"  └─ ❌ Erro ao gerar PDF: {pdf_err}")
                else:
                    self.progress.emit("  └─ RECUPERADO (Relatório já existente)")
                
                # Registrar o PDF no manifesto se ele existir
                if pdf_path.exists():
                    manifest_entry["analysis_files"]["report_pdf"] = f"{pdf_base_name}.pdf"

            # Add to manifest list
            batch_manifest.append(manifest_entry)

class PrnuCompareWorker(QThread):
    """Worker para comparar arquivos investigados por PRNU com arquivos de referência.
    Todos os fingerprints são extraídos do zero."""
    progress = Signal(str)
    progress_val = Signal(int)
    progress_max = Signal(int)
    finished = Signal(bool, str)  # success, message
    
    def __init__(self, external_files: list[Path], reference_files: list[Path],
                 output_dir: Path, case_name: str, config=None):
        super().__init__()
        self.external_files = external_files
        self.reference_files = reference_files
        self.output_dir = output_dir
        self.case_name = case_name
        self.config = config
        self._is_cancelled = False
    
    def cancel(self):
        self._is_cancelled = True
        self.progress.emit("Cancelamento solicitado...")
    
    def _extract_prnu(self, file_path: Path, cm, label: str, idx: int, total: int):
        """Extrai o fingerprint PRNU de um único arquivo."""
        self.progress.emit(f"\n[{idx}/{total}] Extraindo PRNU ({label}): {file_path.name}")
        try:
            prnu_mod = PrnuAnalysisModule(cm)
            prnu_mod.frame_limit = getattr(self.config, 'prnu_frame_limit', 30)
            
            out_filename = f"_prnu_{label}_{file_path.stem}_prnu.json"
            prnu_res = prnu_mod.run(file_path, output_filename=out_filename)
            
            if prnu_res.get("status") == "extracted":
                npy_path = cm.results_dir / prnu_res["fingerprint_file"]
                self.progress.emit("  ✅ Fingerprint extraído com sucesso.")
                return {"name": file_path.name, "path": npy_path}
            else:
                self.progress.emit(f"  ⚠️ Falha: {prnu_res.get('error', 'desconhecido')}")
                return None
        except Exception as e:
            self.progress.emit(f"  ❌ Erro: {e}")
            return None
    
    def run(self):
        try:
            from core.utils import get_timestamp_iso
            timestamp = get_timestamp_iso()
            
            # Criar CaseManager para este job
            cm = CaseManager(self.case_name, base_dir=self.output_dir)
            cm.setup()
            
            total_files = len(self.reference_files) + len(self.external_files)
            self.progress_max.emit(total_files + 1)  # +1 para fase de comparação
            
            # 1. Extrair PRNU de TODOS os arquivos (referência + investigados)
            self.progress.emit(f"🔬 Extraindo PRNU de {total_files} arquivos (tudo do zero)...")
            
            reference_fps = []
            step = 0
            for ref_file in self.reference_files:
                if self._is_cancelled:
                    self.finished.emit(False, "Cancelado")
                    return
                step += 1
                self.progress_val.emit(step)
                fp = self._extract_prnu(ref_file, cm, "ref", step, total_files)
                if fp:
                    reference_fps.append(fp)
            
            external_fps = []
            for ext_file in self.external_files:
                if self._is_cancelled:
                    self.finished.emit(False, "Cancelado")
                    return
                step += 1
                self.progress_val.emit(step)
                fp = self._extract_prnu(ext_file, cm, "inv", step, total_files)
                if fp:
                    external_fps.append(fp)
            
            if not reference_fps:
                self.finished.emit(False, "Nenhum fingerprint de referência pôde ser extraído.")
                return
            if not external_fps:
                self.finished.emit(False, "Nenhum fingerprint dos arquivos investigados pôde ser extraído.")
                return
            
            # 2. Comparar cada investigado com todos os de referência
            self.progress.emit(f"\n📊 Comparando {len(external_fps)} investigado(s) com {len(reference_fps)} referência(s)...")
            self.progress_val.emit(total_files)
            
            comparison_results = []
            
            for ext_fp in external_fps:
                file_comparisons = []
                for ref_fp in reference_fps:
                    if self._is_cancelled:
                        self.finished.emit(False, "Cancelado")
                        return
                    try:
                        result = PrnuAnalysisModule.compare_fingerprints(ext_fp["path"], ref_fp["path"])
                        file_comparisons.append({
                            "existing_file": ref_fp["name"],
                            "pce": result.get("pce", 0),
                            "peak": result.get("peak", 0),
                            "energy": result.get("energy", 0),
                            "match": result.get("match", False),
                            "scaling_note": result.get("scaling_note"),
                            "error": result.get("error")
                        })
                        
                        match_str = "✅ MATCH" if result.get("match") else "—"
                        pce_val = result.get("pce", 0)
                        self.progress.emit(f"  {ext_fp['name']} vs {ref_fp['name']}: PCE={pce_val:.1f} {match_str}")
                    except Exception as e:
                        self.progress.emit(f"  ⚠️ Erro: {ext_fp['name']} vs {ref_fp['name']}: {e}")
                        file_comparisons.append({
                            "existing_file": ref_fp["name"],
                            "pce": 0, "match": False, "error": str(e)
                        })
                
                comparison_results.append({
                    "external_file": ext_fp["name"],
                    "comparisons": file_comparisons
                })
            
            # 3. Salvar JSON
            comparison_data = {
                "type": "prnu_comparison",
                "timestamp": timestamp,
                "case_name": self.case_name,
                "external_files": [fp["name"] for fp in external_fps],
                "existing_files": [fp["name"] for fp in reference_fps],
                "results": comparison_results
            }
            
            json_path = cm.results_dir / "prnu_comparison.json"
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(comparison_data, f, indent=4, ensure_ascii=False)
            
            self.progress.emit(f"\n💾 Resultados salvos em: {json_path}")
            
            # 4. Gerar PDF
            self.progress.emit("\n📝 Gerando relatório PDF...")
            try:
                ReportingModule(cm, config=self.config).generate_prnu_comparison(comparison_data)
                pdf_path = cm.report_dir / "prnu_comparison.pdf"
                if pdf_path.exists():
                    self.progress.emit(f"✅ Relatório PDF gerado em: {cm.report_dir}")
                else:
                    self.progress.emit("⚠️ Arquivo .tex gerado, mas a compilação do PDF falhou.")
                    self.progress.emit("   Verifique se o pdflatex está instalado e no PATH.")
                    self.progress.emit(f"   O .tex pode ser compilado manualmente em: {cm.report_dir}")
            except Exception as rep_err:
                self.progress.emit(f"❌ Erro ao gerar PDF: {rep_err}")
                import traceback
                traceback.print_exc()
            
            self.progress_val.emit(total_files + 1)
            self.finished.emit(True, str(cm.report_dir))
            
        except Exception as e:
            self.progress.emit(f"ERRO: {e}")
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
        
        self.browse_folder_btn = QPushButton("Abrir Pasta (Mídia/Forense)")
        self.browse_folder_btn.clicked.connect(self.browse_folder)
        
        file_layout.addWidget(self.file_input)
        file_layout.addWidget(self.browse_btn)
        file_layout.addWidget(self.browse_folder_btn)
        
        self.settings_btn = QPushButton("Configurações")
        self.settings_btn.clicked.connect(self.open_settings)
        file_layout.addWidget(self.settings_btn)

        self.dashboard_btn = QPushButton("📊 Dashboard Cluster")
        self.dashboard_btn.setStyleSheet(
            "QPushButton { background-color: #8E44AD; color: white; padding: 4px 10px; "
            "border-radius: 3px; font-weight: bold; }"
            "QPushButton:hover { background-color: #7D3C98; }"
        )
        self.dashboard_btn.setToolTip("Abrir o painel de monitoramento do cluster em tempo real")
        self.dashboard_btn.clicked.connect(self.open_dashboard)
        file_layout.addWidget(self.dashboard_btn)

        self.prnu_compare_btn = QPushButton("🔍 Comparar PRNU")
        self.prnu_compare_btn.setStyleSheet(
            "QPushButton { background-color: #2980B9; color: white; padding: 4px 10px; "
            "border-radius: 3px; font-weight: bold; }"
            "QPushButton:hover { background-color: #2471A3; }"
        )
        self.prnu_compare_btn.setToolTip(
            "Comparar arquivos externos por PRNU com os presentes no diretório de trabalho"
        )
        self.prnu_compare_btn.clicked.connect(self.start_prnu_compare)
        file_layout.addWidget(self.prnu_compare_btn)

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
        self.selected_files: list[Path] = [] 
    
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
        media_files: list[Path] = []
        for ext in MEDIA_EXTENSIONS:
            # Use explicit wildcards and type hints to avoid 'Unknown' inference
            media_files.extend(list(folder_path.rglob(f'*{ext}')))
            media_files.extend(list(folder_path.rglob(f'*{ext.upper()}')))
        
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

    def open_dashboard(self):
        """Abre o Dashboard de Monitoramento do Cluster."""
        dlg = ClusterDashboard(self)
        dlg.show()

    def start_prnu_compare(self):
        """Compara arquivos investigados por PRNU com os já selecionados (referência)."""
        # 1. Verificar se há arquivos de referência selecionados
        if not self.selected_files:
            QMessageBox.warning(
                self, "Aviso",
                "Nenhum arquivo de referência selecionado.\n\n"
                "Primeiro selecione os arquivos de referência usando "
                "'Selecionar Arquivos' ou 'Selecionar Pasta'."
            )
            return
        
        # 2. Selecionar arquivos para investigar (comparar)
        filters = (
            "Forensic Files (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.dav "
            "*.jpg *.jpeg *.png *.tif *.tiff *.webp);;"
            "Videos (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.dav);;"
            "Images (*.jpg *.jpeg *.png *.tif *.tiff *.webp)"
        )
        fnames, _ = QFileDialog.getOpenFileNames(
            self, "Selecionar Arquivos para Investigar por PRNU", "", filters
        )
        if not fnames:
            return
        
        external_files = [Path(f) for f in fnames]
        
        # 3. Selecionar diretório de saída (mesmo padrão da análise normal)
        output_dir = QFileDialog.getExistingDirectory(
            self, "Selecionar Pasta para Salvar Resultados da Comparação PRNU"
        )
        if not output_dir:
            return
        
        # 4. Nome do caso
        from PySide6.QtWidgets import QInputDialog
        default_name = f"PRNU_COMPARE_{len(external_files)}_vs_{len(self.selected_files)}"
        case_name, ok = QInputDialog.getText(
            self, "Nome do Caso PRNU",
            "Digite o nome da pasta a ser criada:",
            text=default_name
        )
        if not ok or not case_name.strip():
            return
        case_name = case_name.strip().rstrip('. ')
        
        # 5. Confirmar
        ref_names = "\n".join(f"  • {f.name}" for f in self.selected_files[:5])
        if len(self.selected_files) > 5:
            ref_names += f"\n  ... e mais {len(self.selected_files) - 5} arquivo(s)"
        ext_names = "\n".join(f"  • {f.name}" for f in external_files[:5])
        if len(external_files) > 5:
            ext_names += f"\n  ... e mais {len(external_files) - 5} arquivo(s)"
        
        reply = QMessageBox.question(
            self, "Confirmar Comparação PRNU",
            f"REFERÊNCIA ({len(self.selected_files)} arquivo(s)):\n{ref_names}\n\n"
            f"INVESTIGADOS ({len(external_files)} arquivo(s)):\n{ext_names}\n\n"
            f"Todos os PRNUs serão calculados do zero.\n"
            f"O relatório PDF será gerado automaticamente.\n\nContinuar?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        # 6. Iniciar worker
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.browse_btn.setEnabled(False)
        self.browse_folder_btn.setEnabled(False)
        self.settings_btn.setEnabled(False)
        self.prnu_compare_btn.setEnabled(False)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.log_output.clear()
        
        config = load_config()
        reference_files = [Path(f) for f in self.selected_files]
        
        self.worker = PrnuCompareWorker(
            external_files=external_files,
            reference_files=reference_files,
            output_dir=Path(output_dir),
            case_name=case_name.strip(),
            config=config
        )
        self.worker.progress.connect(self.update_log)
        self.worker.progress_max.connect(self.progress_bar.setMaximum)
        self.worker.progress_val.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self.analysis_finished)
        self.worker.start()
        
        self.log_output.append("🔍 Comparação PRNU iniciada.")
        self.log_output.append(f"📂 Referência: {len(reference_files)} arquivo(s)")
        for rf in reference_files:
            self.log_output.append(f"  • {rf.name}")
        self.log_output.append(f"📁 Investigados: {len(external_files)} arquivo(s)")
        for ef in external_files:
            self.log_output.append(f"  • {ef.name}")
        self.log_output.append("")
    
    def start_analysis(self):
        if not self.selected_files:
            QMessageBox.critical(self, "Erro", "Nenhum arquivo selecionado!")
            return
            
        # Solicitar diretório de saída
        output_dir = QFileDialog.getExistingDirectory(self, "Selecionar Pasta para Salvar Relatórios")
        if not output_dir:
            return  # Usuário cancelou
        
        # Verificar se o diretório de saída é acessível e tem permissão de escrita
        output_path = Path(output_dir)
        try:
            # Teste de escrita real: cria e remove um arquivo temporário
            test_file = output_path / ".forensic_write_test"
            test_file.write_text("test", encoding="utf-8")
            test_file.unlink()
        except OSError as e:
            QMessageBox.critical(
                self, "Erro de Acesso",
                f"Não foi possível escrever no diretório selecionado:\n\n"
                f"{output_dir}\n\n"
                f"Erro: {e}\n\n"
                f"Verifique se:\n"
                f"• O caminho ainda existe (Google Drive sincronizado?)\n"
                f"• Você tem permissão de escrita nesse local\n"
                f"• O disco não está cheio"
            )
            return
            
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
        # Sanitizar: remover espaços nas extremidades e caracteres inválidos para Windows
        case_name = case_name.strip().rstrip('. ')
            
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.browse_btn.setEnabled(False)
        self.browse_folder_btn.setEnabled(False)
        self.settings_btn.setEnabled(False)
        self.prnu_compare_btn.setEnabled(False)
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
        self.prnu_compare_btn.setEnabled(True)
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
