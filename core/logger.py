"""
Logger para auditoria de eventos forenses.

Este módulo fornece um logger que grava eventos estruturados em JSON,
adequado para trilhas de auditoria em análises forenses.
"""
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional, TextIO

from .utils import get_timestamp_iso

_module_logger = logging.getLogger(__name__)


class Logger:
    """Logger estruturado para eventos forenses.
    
    Grava eventos em formato JSON-Lines (JSONL) com timestamp,
    tipo de evento e detalhes. Implementa retry para lidar com
    file locking no Windows.
    
    Attributes:
        log_path: Caminho do arquivo de log.
        MAX_RETRIES: Número máximo de tentativas de escrita.
        RETRY_DELAY: Intervalo entre tentativas (segundos).
    
    Example:
        >>> logger = Logger(Path("case/execution.log"))
        >>> logger.log("ANALYSIS_START", {"file": "video.mp4"})
    """
    
    MAX_RETRIES: int = 5
    RETRY_DELAY: float = 0.1
    
    def __init__(self, log_path: Path) -> None:
        """Inicializa o logger.
        
        Args:
            log_path: Caminho para o arquivo de log.
        """
        self.log_path = Path(log_path)
        self._ensure_log_file()
    
    def _ensure_log_file(self) -> None:
        """Garante que o arquivo de log e diretório existam."""
        if not self.log_path.parent.exists():
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.touch()
    
    def _open_with_retry(self, mode: str) -> TextIO:
        """Abre arquivo com retry para lidar com locking.
        
        Args:
            mode: Modo de abertura ('r', 'w', 'a').
            
        Returns:
            Handle do arquivo aberto.
            
        Raises:
            PermissionError: Se não conseguir abrir após MAX_RETRIES.
            IOError: Se falhar por outro motivo.
        """
        last_error: Optional[Exception] = None
        
        for attempt in range(self.MAX_RETRIES):
            try:
                return open(self.log_path, mode, encoding='utf-8')
            except (PermissionError, BlockingIOError) as e:
                last_error = e
                time.sleep(self.RETRY_DELAY)
        
        if last_error:
            raise last_error
        raise IOError("Could not open log file after retries")
    
    def log(
        self,
        event_type: str,
        details: Optional[dict[str, Any]] = None
    ) -> None:
        """Registra um evento com timestamp.
        
        Args:
            event_type: Tipo do evento (ex: "START_MODULE", "ERROR").
            details: Dicionário com detalhes adicionais.
        """
        if details is None:
            details = {}
        
        timestamp = get_timestamp_iso()
        
        event_payload = {
            "timestamp": timestamp,
            "event_type": event_type,
            "details": details
        }
        
        try:
            with self._open_with_retry('a') as f:
                f.write(json.dumps(event_payload, ensure_ascii=False) + "\n")
        except Exception as e:
            _module_logger.warning(
                "Failed to write to log file %s: %s",
                self.log_path,
                e
            )
    
    def read_events(self) -> list[dict[str, Any]]:
        """Lê todos os eventos do log.
        
        Returns:
            Lista de eventos como dicionários.
        """
        events = []
        try:
            with self._open_with_retry('r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            _module_logger.warning(
                                "Invalid JSON line in log: %s",
                                line[:50]
                            )
        except Exception as e:
            _module_logger.warning("Failed to read log file: %s", e)
        
        return events
