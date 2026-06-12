"""
Dashboard de Monitoramento do Cluster.
Janela independente que rastreia periodicamente o diretório de resultados
e apresenta o status de processamento de todos os PCs e instâncias.
"""

import json
import socket
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

# Extensões de mídia suportadas pelo app (para contar arquivos de origem)
MEDIA_EXTENSIONS = {
    '.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.dav',
    '.jpg', '.jpeg', '.png', '.tif', '.tiff', '.webp',
    '.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.opus', '.wma'
}


class ClusterDashboard(QDialog):
    """Janela de monitoramento em tempo real do cluster de processamento."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🖥️ Dashboard do Cluster - Monitoramento em Tempo Real")
        self.resize(1100, 750)
        self.setMinimumSize(900, 550)

        self.case_dir: Path | None = None          # Pasta raiz do caso
        self.results_dir: Path | None = None       # Pasta results/ dentro do caso
        self.source_dir: Path | None = None        # Pasta onde estão os arquivos originais (para contar total)
        self.total_input_files: int = 0
        self.scan_interval_sec: int = 5

        # Timer de auto-refresh
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.scan_directory)

        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)

        # ── Barra Superior: Seleção de pasta e controles ──
        top_bar = QHBoxLayout()

        self.dir_label = QLabel("Pasta do caso:")
        self.dir_label.setStyleSheet("font-weight: bold;")
        top_bar.addWidget(self.dir_label)

        self.dir_display = QLabel("(nenhuma pasta selecionada)")
        self.dir_display.setStyleSheet("color: #888; font-style: italic;")
        top_bar.addWidget(self.dir_display, stretch=1)

        self.browse_btn = QPushButton("📂 Selecionar Pasta do Caso")
        self.browse_btn.setStyleSheet(
            "QPushButton { background-color: #3498DB; color: white; padding: 6px 14px; "
            "border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background-color: #2980B9; }"
        )
        self.browse_btn.clicked.connect(self._select_directory)
        top_bar.addWidget(self.browse_btn)

        main_layout.addLayout(top_bar)

        # ── Linha 2: Total de arquivos + Intervalo + Controles ──
        config_bar = QHBoxLayout()

        config_bar.addWidget(QLabel("Total de arquivos no lote:"))
        self.total_spin = QSpinBox()
        self.total_spin.setRange(1, 9999)
        self.total_spin.setValue(160)
        self.total_spin.setToolTip(
            "Informe o número total de arquivos que devem ser processados.\n"
            "Este valor é usado para calcular a porcentagem e os pendentes.\n"
            "O dashboard tenta detectar automaticamente, mas você pode ajustar manualmente."
        )
        self.total_spin.setStyleSheet("font-weight: bold; padding: 3px;")
        self.total_spin.valueChanged.connect(self._on_total_changed)
        config_bar.addWidget(self.total_spin)

        config_bar.addSpacing(20)

        config_bar.addWidget(QLabel("Intervalo (s):"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(2, 120)
        self.interval_spin.setValue(5)
        self.interval_spin.setToolTip("Intervalo de atualização automática em segundos")
        self.interval_spin.valueChanged.connect(self._update_interval)
        config_bar.addWidget(self.interval_spin)

        config_bar.addSpacing(20)

        self.toggle_btn = QPushButton("▶ Iniciar Monitoramento")
        self.toggle_btn.setStyleSheet(
            "QPushButton { background-color: #27AE60; color: white; padding: 6px 14px; "
            "border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background-color: #229954; }"
        )
        self.toggle_btn.setEnabled(False)
        self.toggle_btn.clicked.connect(self._toggle_monitoring)
        config_bar.addWidget(self.toggle_btn)

        self.refresh_btn = QPushButton("🔄 Atualizar Agora")
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.clicked.connect(self.scan_directory)
        config_bar.addWidget(self.refresh_btn)

        config_bar.addStretch()
        main_layout.addLayout(config_bar)

        # ── Separador ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(sep)

        # ── Painel de Resumo (Cards) ──
        # Agora temos 4 cards com significados claros:
        #   Total | Concluídos | Em Processamento (locks ativos) | Pendentes
        summary_group = QGroupBox("📊 Resumo Geral do Lote")
        summary_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 13px; border: 1px solid #ccc; "
            "border-radius: 6px; margin-top: 10px; padding-top: 14px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; }"
        )
        summary_layout = QHBoxLayout(summary_group)

        self.card_total = self._create_card("Total do Lote", "0", "#2C3E50")
        self.card_done = self._create_card("✅ Concluídos", "0", "#27AE60")
        self.card_processing = self._create_card(
            "⚙️ Em Processamento\n(arquivos com lock)", "0", "#F39C12"
        )
        self.card_pending = self._create_card("⏳ Pendentes", "0", "#E74C3C")

        summary_layout.addWidget(self.card_total)
        summary_layout.addWidget(self.card_done)
        summary_layout.addWidget(self.card_processing)
        summary_layout.addWidget(self.card_pending)

        main_layout.addWidget(summary_group)

        # ── Progress Bar Geral ──
        self.overall_progress = QProgressBar()
        self.overall_progress.setTextVisible(True)
        self.overall_progress.setFormat("%p% concluído (%v / %m arquivos)")
        self.overall_progress.setStyleSheet(
            "QProgressBar { height: 22px; border: 1px solid #bbb; border-radius: 4px; "
            "text-align: center; background: #ECF0F1; font-weight: bold; }"
            "QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 #27AE60, stop:1 #2ECC71); border-radius: 3px; }"
        )
        main_layout.addWidget(self.overall_progress)

        # ── Tabela de Nós/Instâncias ──
        nodes_group = QGroupBox("🖥️ PCs e Instâncias Conectados ao Cluster")
        nodes_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 12px; border: 1px solid #ccc; "
            "border-radius: 6px; margin-top: 10px; padding-top: 14px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; }"
        )
        nodes_layout = QVBoxLayout(nodes_group)
        self.nodes_table = QTableWidget()
        self.nodes_table.setColumnCount(5)
        self.nodes_table.setHorizontalHeaderLabels([
            "PC (Hostname)", "Instância (PID)", "Status",
            "Arquivo em Processamento", "Fase Atual"
        ])
        # Permitir que o usuário redimensione as colunas; a última estica para preencher
        header = self.nodes_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        # Larguras iniciais razoáveis
        self.nodes_table.setColumnWidth(0, 180)
        self.nodes_table.setColumnWidth(1, 100)
        self.nodes_table.setColumnWidth(2, 110)
        self.nodes_table.setColumnWidth(3, 320)
        # coluna 4 (Fase) estica automaticamente
        self.nodes_table.setAlternatingRowColors(True)
        self.nodes_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.nodes_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.nodes_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.nodes_table.customContextMenuRequested.connect(self._show_context_menu)
        self.nodes_table.setStyleSheet(
            "QTableWidget { gridline-color: #ddd; }"
            "QTableWidget::item { padding: 4px; }"
        )
        nodes_layout.addWidget(self.nodes_table)
        main_layout.addWidget(nodes_group, stretch=1)

        # ── Barra de Status inferior ──
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Aguardando seleção de pasta...")
        self.status_label.setStyleSheet("color: #7F8C8D; font-size: 11px;")
        status_layout.addWidget(self.status_label, stretch=1)

        self.clean_locks_btn = QPushButton("🧹 Limpar Arquivos Órfãos")
        self.clean_locks_btn.setStyleSheet(
            "QPushButton { background-color: #E74C3C; color: white; padding: 5px 12px; "
            "border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background-color: #C0392B; }"
        )
        self.clean_locks_btn.setEnabled(False)
        self.clean_locks_btn.setToolTip(
            "Remove arquivos temporários órfãos do cluster:\n\n"
            "• Locks (.lock): indicam que um PC está processando um arquivo.\n"
            "  Se o programa travou, o lock fica órfão e bloqueia outros PCs.\n\n"
            "• Registros de nó (_node_*.json): indicam que um PC está conectado.\n"
            "  Se o programa travou, o registro fica órfão.\n\n"
            "⚠️ Use SOMENTE se todos os PCs estão PARADOS."
        )
        self.clean_locks_btn.clicked.connect(self._clean_locks)
        status_layout.addWidget(self.clean_locks_btn)

        main_layout.addLayout(status_layout)

    def _create_card(self, title: str, value: str, color: str) -> QFrame:
        """Cria um 'card' visual para o painel de resumo."""
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background-color: {color}; border-radius: 8px; padding: 8px; }}"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 6, 10, 6)
        card_layout.setSpacing(2)

        lbl_title = QLabel(title)
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 11px; font-weight: bold;")

        lbl_value = QLabel(value)
        lbl_value.setAlignment(Qt.AlignCenter)
        lbl_value.setStyleSheet("color: white; font-size: 24px; font-weight: bold;")
        lbl_value.setObjectName("card_value")

        card_layout.addWidget(lbl_title)
        card_layout.addWidget(lbl_value)
        return card

    def _update_card_value(self, card: QFrame, value):
        lbl = card.findChild(QLabel, "card_value")
        if lbl:
            lbl.setText(str(value))

    def _select_directory(self):
        """Pede ao usuário para selecionar a pasta do caso (que contém results/)."""
        folder = QFileDialog.getExistingDirectory(
            self, "Selecionar Pasta do Caso (contém 'results/')"
        )
        if not folder:
            return

        folder_path = Path(folder)

        self.case_dir = folder_path
        
        # Tentar encontrar a subpasta 'results' automaticamente
        if (folder_path / "results").is_dir():
            self.results_dir = folder_path / "results"
        elif folder_path.name == "results":
            self.results_dir = folder_path
            self.case_dir = folder_path.parent
        else:
            # Procurar recursivamente (1 nível)
            for child in folder_path.iterdir():
                if child.is_dir() and (child / "results").is_dir():
                    self.results_dir = child / "results"
                    self.case_dir = child
                    break
            else:
                # Usar a pasta diretamente
                self.results_dir = folder_path

        if self.results_dir:
            self.dir_display.setText(str(self.case_dir))
            self.dir_display.setStyleSheet("color: #2C3E50; font-style: normal; font-weight: bold;")
        
        self.toggle_btn.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        self.clean_locks_btn.setEnabled(True)

        # Tentar auto-detectar o total de arquivos
        self._discover_total_files()

        # Fazer um scan imediato
        self.scan_directory()

    def _discover_total_files(self):
        """Tenta descobrir o total de arquivos usando todas as fontes disponíveis.
        NUNCA diminui o valor atual do spinbox — só atualiza se encontrar um valor MAIOR."""
        res_dir = self.results_dir
        if not res_dir:
            return

        candidates: list[int] = []

        # Fonte 1: _node_*.json (fonte mais confiável — total exato informado pela instância)
        for node_file in res_dir.glob("_node_*.json"):
            try:
                with open(node_file, encoding='utf-8') as f:
                    node_data = json.load(f)
                node_total = node_data.get("total_files", 0)
                if node_total > 0:
                    candidates.append(node_total)
            except Exception:
                pass

        # Fonte 2: Maior índice numérico nos prefixos de arquivos (XX_name.ext)
        max_idx: int = 0
        for f in res_dir.glob("*"):
            name = f.stem
            parts = name.split("_", 1)
            if len(parts) > 1 and parts[0].isdigit():
                idx = int(parts[0])
                if idx > max_idx:
                    max_idx = idx
        if max_idx > 0:
            candidates.append(max_idx)

        # Fonte 3: Tamanho do manifesto
        manifest_path = res_dir / "batch_manifest.json"
        if manifest_path.exists():
            try:
                with open(manifest_path, encoding='utf-8') as f:
                    manifest_data = json.load(f)
                    manifest_count = len(manifest_data)
                if manifest_count > 0:
                    candidates.append(manifest_count)
            except Exception:
                pass

        # Fonte 4: Manifesto + locks ativos (cobertura mínima observada)
        lock_count = len(list(res_dir.glob("*.lock")))
        if manifest_path.exists():
            try:
                with open(manifest_path, encoding='utf-8') as f:
                    m_data = json.load(f)
                    m_count = len(m_data)
                candidates.append(m_count + lock_count)
            except Exception:
                pass

        if candidates:
            best = max(candidates)
            # Só atualiza se for MAIOR que o valor atual (nunca diminuir)
            if best > self.total_spin.value():
                self.total_spin.setValue(best)
                self.total_input_files = best

    def _on_total_changed(self, value):
        """Quando o usuário altera manualmente o total."""
        self.total_input_files = value
        # Recalcular se já temos dados
        if self.results_dir:
            self.scan_directory()

    def _toggle_monitoring(self):
        if self.refresh_timer.isActive():
            self.refresh_timer.stop()
            self.toggle_btn.setText("▶ Iniciar Monitoramento")
            self.toggle_btn.setStyleSheet(
                "QPushButton { background-color: #27AE60; color: white; padding: 6px 14px; "
                "border-radius: 4px; font-weight: bold; }"
                "QPushButton:hover { background-color: #229954; }"
            )
            self.status_label.setText("Monitoramento pausado.")
        else:
            interval_ms = self.interval_spin.value() * 1000
            self.refresh_timer.start(interval_ms)
            self.toggle_btn.setText("⏸ Pausar Monitoramento")
            self.toggle_btn.setStyleSheet(
                "QPushButton { background-color: #E67E22; color: white; padding: 6px 14px; "
                "border-radius: 4px; font-weight: bold; }"
                "QPushButton:hover { background-color: #D35400; }"
            )
            self.status_label.setText(
                f"Monitoramento ativo (atualiza a cada {self.interval_spin.value()}s)..."
            )

    def _update_interval(self, value):
        if self.refresh_timer.isActive():
            self.refresh_timer.setInterval(value * 1000)

    def scan_directory(self):
        """Escaneia o diretório e atualiza todas as tabelas e cards."""
        if not self.results_dir or not self.results_dir.exists():
            self.status_label.setText("⚠️ Pasta não encontrada!")
            return

        res_dir = self.results_dir
        c_dir = self.case_dir or res_dir.parent
        now = datetime.now().strftime("%H:%M:%S")

        # Pré-indexar arquivos existentes para detectar fase de processamento
        existing_jsons = {f.name for f in res_dir.glob("*.json")}
        
        # Encontrar pasta de relatórios
        report_dir = c_dir / "report"
        existing_pdfs = set()
        if report_dir.exists():
            existing_pdfs = {f.name for f in report_dir.glob("*.pdf")}

        # ── 1. Carregar manifesto (arquivos concluídos) ──
        manifest_path = res_dir / "batch_manifest.json"
        completed_files = {}  # filename -> entry
        if manifest_path.exists():
            try:
                with open(manifest_path, encoding='utf-8') as f:
                    manifest = json.load(f)
                for entry in manifest:
                    fname = entry.get("filename", "")
                    if fname:
                        completed_files[fname] = entry
            except Exception as e:
                self.status_label.setText(f"⚠️ Erro ao ler manifesto: {e}")

        # ── 2. Escanear locks (arquivos em processamento) ──
        active_locks = {}  # lock_stem -> {"host": ..., "pid": ..., "filename": ...}
        for lock_file in res_dir.glob("*.lock"):
            try:
                content = lock_file.read_text(encoding='utf-8').strip()
                host, pid = "?", "?"
                if ":" in content:
                    parts = content.split(":", 1)
                    host, pid = parts[0], parts[1]
                else:
                    host = content

                # Extrair nome do arquivo original do nome do lock
                # formato: XX_filename.lock
                lock_stem = lock_file.stem
                # Remover prefixo numérico (ex: "04_video_name" -> "video_name")
                parts = lock_stem.split("_", 1)
                display_name = parts[1] if len(parts) > 1 and parts[0].isdigit() else lock_stem

                active_locks[lock_stem] = {
                    "host": host,
                    "pid": pid,
                    "display_name": display_name,
                    "lock_file": lock_file.name,
                    "lock_id": content
                }
            except Exception:
                active_locks[lock_file.stem] = {
                    "host": "?", "pid": "?",
                    "display_name": lock_file.stem,
                    "lock_file": lock_file.name,
                    "lock_id": "???"
                }

        # ── 3. Computar estatísticas ──
        n_completed = len(completed_files)
        n_processing = len(active_locks)

        # Re-verificar _node_*.json a cada scan (pode aparecer após a primeira leitura)
        self._discover_total_files()

        # Usar o total definido pelo usuário (spin box), que é a fonte da verdade
        total = self.total_spin.value()
        n_pending = max(0, total - n_completed - n_processing)

        # ── 4. Carregar heartbeats dos nós (_node_*.json) ──
        node_heartbeats = {}  # "host:pid" -> {"last_heartbeat": datetime, "data": dict}
        for node_file in res_dir.glob("_node_*.json"):
            try:
                with open(node_file, encoding='utf-8') as f:
                    ndata = json.load(f)
                hb_str = ndata.get("last_heartbeat") or ndata.get("started_at", "")
                if hb_str:
                    hb_time = datetime.fromisoformat(hb_str)
                else:
                    # Usar mtime do arquivo como fallback
                    hb_time = datetime.fromtimestamp(node_file.stat().st_mtime)
                h = ndata.get("hostname", "?")
                p = str(ndata.get("pid", "?"))
                key = f"{h}:{p}"
                node_heartbeats[key] = {
                    "last_heartbeat": hb_time,
                    "data": ndata
                }
            except Exception:
                pass

        # ── 5. Agrupar por nó (host:pid) ──
        nodes: dict[str, dict] = {}  # "host:pid" -> {"host", "pid", "files": [...]}
        for lock_info in active_locks.values():
            node_key = f"{lock_info['host']}:{lock_info['pid']}"
            if node_key not in nodes:
                nodes[node_key] = {
                    "host": lock_info["host"],
                    "pid": lock_info["pid"],
                    "files": []
                }
            nodes[node_key]["files"].append(lock_info["display_name"])

        # ── 6. Atualizar Cards ──
        self._update_card_value(self.card_total, total)
        self._update_card_value(self.card_done, n_completed)
        self._update_card_value(self.card_processing, n_processing)
        self._update_card_value(self.card_pending, n_pending)

        # ── 7. Progress Bar ──
        self.overall_progress.setMaximum(max(total, 1))
        self.overall_progress.setValue(n_completed)

        # ── 8. Tabela de Nós ──
        self.nodes_table.setRowCount(len(nodes))
        my_host = socket.gethostname()
        now_dt = datetime.now()

        # Thresholds para status
        WARN_MINUTES = 10   # Sem heartbeat por 10 min → aviso
        DEAD_MINUTES = 30   # Sem heartbeat por 30 min → provavelmente caiu

        for row, (node_key, node_info) in enumerate(sorted(nodes.items())):
            host = node_info["host"]
            pid = node_info["pid"]
            n_files = len(node_info["files"])

            is_self = (host == my_host)

            # Hostname
            host_item = QTableWidgetItem(host)
            host_item.setData(Qt.UserRole, host)  # Guardar valor bruto para busca de locks
            if is_self:
                host_item.setText(f"⭐ {host} (ESTE PC)")
                host_item.setForeground(QColor("#2980B9"))
            host_item.setFont(QFont("", -1, QFont.Bold))
            self.nodes_table.setItem(row, 0, host_item)

            # PID
            pid_item = QTableWidgetItem(str(pid))
            pid_item.setData(Qt.UserRole, str(pid))
            self.nodes_table.setItem(row, 1, pid_item)

            # Status (baseado em heartbeat)
            hb_info = node_heartbeats.get(node_key)
            if hb_info:
                elapsed = now_dt - hb_info["last_heartbeat"]
                elapsed_min = elapsed.total_seconds() / 60

                if elapsed_min < WARN_MINUTES:
                    status_text = "🟢 Ativo"
                    status_color = "#27AE60"
                elif elapsed_min < DEAD_MINUTES:
                    status_text = f"⚠️ Sem resposta ({int(elapsed_min)}min)"
                    status_color = "#E67E22"
                else:
                    status_text = f"🔴 Offline ({int(elapsed_min)}min)"
                    status_color = "#E74C3C"
            else:
                # Sem _node_*.json → versão antiga ou registro perdido
                # Usar mtime do lock como estimativa
                lock_ages = []
                for li in active_locks.values():
                    if li["host"] == host and li["pid"] == pid:
                        lock_path = self.results_dir / li["lock_file"]
                        if lock_path.exists():
                            try:
                                age = (now_dt - datetime.fromtimestamp(lock_path.stat().st_mtime)).total_seconds() / 60
                                lock_ages.append(age)
                            except Exception:
                                pass

                if lock_ages:
                    oldest = max(lock_ages)
                    if oldest < WARN_MINUTES:
                        status_text = "🟢 Ativo (sem heartbeat)"
                        status_color = "#27AE60"
                    elif oldest < DEAD_MINUTES:
                        status_text = f"⚠️ Lock antigo ({int(oldest)}min)"
                        status_color = "#E67E22"
                    else:
                        status_text = f"🔴 Provável queda ({int(oldest)}min)"
                        status_color = "#E74C3C"
                else:
                    status_text = "❓ Desconhecido"
                    status_color = "#7F8C8D"

            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(QColor(status_color))
            status_item.setFont(QFont("", -1, QFont.Bold))
            self.nodes_table.setItem(row, 2, status_item)

            # Arquivo em processamento
            current_file = node_info["files"][0] if n_files >= 1 else "—"
            file_item = QTableWidgetItem(current_file)
            self.nodes_table.setItem(row, 3, file_item)

            # Fase do processamento (detectar pelos JSONs existentes)
            node_lock_stem = None
            for ls, li in active_locks.items():
                if li["host"] == host and li["pid"] == pid:
                    node_lock_stem = ls
                    break
            phase = self._detect_phase(node_lock_stem, existing_jsons, existing_pdfs) if node_lock_stem else "—"
            phase_item = QTableWidgetItem(phase)
            phase_item.setForeground(QColor("#E67E22"))
            phase_item.setFont(QFont("", -1, QFont.Bold))
            self.nodes_table.setItem(row, 4, phase_item)

        if not nodes:
            self.nodes_table.setRowCount(1)
            empty_item = QTableWidgetItem(
                "Nenhum nó processando no momento (nenhum arquivo .lock encontrado)"
            )
            empty_item.setForeground(QColor("#999"))
            empty_item.setFont(QFont("", -1, -1, True))
            self.nodes_table.setItem(0, 0, empty_item)
            self.nodes_table.setSpan(0, 0, 1, 5)

        # ── 8. Status bar ──
        pct = (n_completed / total * 100) if total > 0 else 0
        self.status_label.setText(
            f"Última atualização: {now} | "
            f"{n_completed}/{total} concluídos ({pct:.1f}%) | "
            f"{n_processing} processando ({len(nodes)} nó(s)) | "
            f"{n_pending} pendentes"
        )

    def _detect_phase(self, lock_stem: str, existing_jsons: set, existing_pdfs: set) -> str:
        """Detecta a fase atual de processamento de um arquivo.
        
        Agora inclui a fase de Relatório PDF.
        """
        # Ordem das fases (sufixo do arquivo -> nome amigável da PRÓXIMA fase)
        phases = [
            ("file_analysis",     "1/7 Metadados"),
            ("continuity",        "2/7 Continuidade"),
            ("compression",       "3/7 Compressão"),
            ("prnu",              "4/7 PRNU"),
            ("structure",         "5/7 Estrutura"),
            ("quantization",      "6/7 Quantização"),
            ("deepfake_analysis", "7/7 Deepfake"),
            ("image_analysis",    "Imagem Forense"),
            ("audio_analysis",    "Áudio Forense"),
            ("audio_deepfake",    "Deepfake de Voz"),
            ("report_pdf",        "Gerando Relatório"),
        ]
        
        last_completed: str | None = None
        for suffix, label in phases:
            if suffix == "report_pdf":
                # PDF nomenclature is different: relatorio_XX_filename.pdf
                # lock_stem is XX_filename
                pdf_name = f"relatorio_{lock_stem}.pdf"
                if pdf_name in existing_pdfs:
                    last_completed = label
            else:
                json_name = f"{lock_stem}_{suffix}.json"
                if json_name in existing_jsons:
                    last_completed = label
        
        if last_completed is None:
            return "1/7 Metadados"
        
        # Encontrar a próxima fase
        for i, (_suffix, label) in enumerate(phases):
            if label == last_completed:
                if i + 1 < len(phases):
                    return str(phases[i+1][1])
                else:
                    return "Finalizando..."
        
        return str(last_completed or "1/7 Metadados")

    def _clean_locks(self):
        """Remove arquivos órfãos (.lock e _node_*.json) se estiverem parados há muito tempo."""
        res_dir = self.results_dir
        if not res_dir:
            return

        import time
        
        # Limite de segurança: 10 minutos sem alteração
        STALE_THRESHOLD: int = 10
        now: float = time.time()
        
        all_locks: list[Path] = list(res_dir.glob("*.lock"))
        all_node_files: list[Path] = list(res_dir.glob("_node_*.json"))
        
        stale_locks: list[Path] = []
        stale_nodes: list[Path] = []
        
        for lf in all_locks:
            try:
                if (now - lf.stat().st_mtime) / 60 > STALE_THRESHOLD:
                    stale_locks.append(lf)
            except Exception:
                pass

        for nf in all_node_files:
            try:
                if (now - nf.stat().st_mtime) / 60 > STALE_THRESHOLD:
                    stale_nodes.append(nf)
            except Exception:
                pass

        orphans = stale_locks + stale_nodes

        if not orphans:
            QMessageBox.information(
                self, "Tudo limpo!", 
                f"Nenhum arquivo órfão (vencido há >{STALE_THRESHOLD}min) encontrado.\n\n"
                f"Arquivos ativos: {len(all_locks)} locks, {len(all_node_files)} nós."
            )
            return

        # Montar lista de detalhes
        details = [f"⚠️ Serão removidos apenas arquivos inativos há mais de {STALE_THRESHOLD} min.\n"]
        
        if stale_locks:
            details.append(f"\n🔒 {len(stale_locks)} lock(s) expirado(s):")
            for lf in stale_locks[:5]:
                try:
                    content = lf.read_text(encoding='utf-8').strip()
                    details.append(f"  • {lf.name}  ← {content}")
                except Exception:
                    details.append(f"  • {lf.name}")
            if len(stale_locks) > 5:
                details.append(f"  ... (+{len(stale_locks)-5} outros)")

        if stale_nodes:
            details.append(f"\n📋 {len(stale_nodes)} registro(s) de nó expirados:")
            for nf in stale_nodes[:5]:
                try:
                    data = json.loads(nf.read_text(encoding='utf-8'))
                    details.append(f"  • {nf.name}  ← {data.get('hostname','?')} (Inativo)")
                except Exception:
                    details.append(f"  • {nf.name}")
            if len(stale_nodes) > 5:
                details.append(f"  ... (+{len(stale_nodes)-5} outros)")

        reply = QMessageBox.warning(
            self, "🧹 Limpar Arquivos Órfãos",
            f"Encontrado(s) {len(orphans)} arquivo(s) ÓRFÃOS (sem atividade recente).\n\n"
            "Arquivos ATIVOS (atuais) foram preservados automaticamente.\n"
            + "\n".join(details) + "\n\nDeseja remover os arquivos listados acima?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            removed = 0
            errors = 0
            for orphan_file in orphans:
                try:
                    # Tentar abrir em modo exclusivo para garantir que ninguém está usando
                    # (Fallback adicional ao mtime)
                    orphan_file.unlink()
                    removed += 1
                except Exception:
                    errors += 1

            msg = f"✅ {removed} arquivo(s) expirado(s) removido(s) com sucesso."
            if errors > 0:
                msg += f"\n⚠️ {errors} arquivo(s) não puderam ser removidos (podem estar em uso)."

            QMessageBox.information(self, "Limpeza Concluída", msg)
            self.scan_directory()

    def _show_context_menu(self, pos):
        """Exibe menu de contexto ao clicar com botão direito em um nó."""
        item = self.nodes_table.itemAt(pos)
        if not item:
            return
        
        row = item.row()
        host_item = self.nodes_table.item(row, 0)
        pid_item = self.nodes_table.item(row, 1)
        
        # Recuperar valores brutos (sem decorações de "ESTE PC" ou estrelas)
        host = host_item.data(Qt.UserRole) or host_item.text()
        pid = pid_item.data(Qt.UserRole) or pid_item.text()
        
        if "Nenhum nó" in host:
            return

        menu = QMenu(self)
        # Estilo para o menu de contexto
        menu.setStyleSheet(
            "QMenu { background: white; border: 1px solid #ccc; padding: 4px; }"
            "QMenu::item { padding: 6px 20px; border-radius: 4px; }"
            "QMenu::item:selected { background: #3498DB; color: white; }"
        )
        
        action_release = menu.addAction(f"🚀 Liberar Arquivos de {host} (Forçar)")
        action_release.triggered.connect(lambda: self._force_release_node(host, pid))
        
        menu.exec(self.nodes_table.viewport().mapToGlobal(pos))

    def _force_release_node(self, host, pid):
        """Remove manualmente as travas e registros de um nó específico."""
        res_dir = self.results_dir
        if res_dir is None:
            return

        reply = QMessageBox.question(
            self, "🚀 Forçar Liberação",
            f"Deseja forçar a liberação dos arquivos do nó {host} (PID {pid})?\n\n"
            "Isso apagará os arquivos .lock e o registro do nó.\n"
            "⚠️ Use apenas se o computador estiver TRAVADO ou OFFLINE!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            removed = 0
            # 1. Procurar e remover o arquivo de registro do nó
            node_file = self.results_dir / f"_node_{host}_{pid}.json"
            if node_file.exists():
                try:
                    node_file.unlink()
                    removed += 1
                except Exception:
                    pass
                
            # 2. Procurar e remover arquivos .lock que contenham "HOSTNAME:PID"
            target_id = f"{host}:{pid}"
            for lf in self.results_dir.glob("*.lock"):
                try:
                    content = lf.read_text(encoding='utf-8').strip()
                    if content == target_id:
                        lf.unlink()
                        removed += 1
                except Exception:
                    pass
                
            QMessageBox.information(
                self, "Ação Concluída", 
                f"Foram removidos {removed} arquivo(s) associados a este nó.\n\n"
                "As tarefas agora estão livres para serem pegas por outros computadores."
            )
            self.scan_directory()

    def closeEvent(self, event):
        """Para o timer ao fechar a janela."""
        self.refresh_timer.stop()
        super().closeEvent(event)
