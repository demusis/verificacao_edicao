import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
from .utils import get_timestamp_iso

class Logger:
    """Logger simples que grava eventos em texto/JSON sem hash."""
    
    MAX_RETRIES = 5
    RETRY_DELAY = 0.1

    def __init__(self, log_path: Path):
        self.log_path = Path(log_path)
        self._ensure_log_file()

    def _ensure_log_file(self):
        """Garante que o arquivo de log e diretório existam."""
        if not self.log_path.parent.exists():
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.touch()

    def _open_with_retry(self, mode: str):
        """Tenta abrir o arquivo com retries para lidar com locking do Windows."""
        last_error = None
        for i in range(self.MAX_RETRIES):
            try:
                return open(self.log_path, mode, encoding='utf-8')
            except (PermissionError, BlockingIOError) as e:
                last_error = e
                time.sleep(self.RETRY_DELAY)
        raise last_error if last_error else IOError("Could not open log file")

    def log(self, event_type: str, details: Dict[str, Any] = None) -> str:
        """Registra um evento com timestamp."""
        if details is None:
            details = {}
        
        timestamp = get_timestamp_iso()
        
        event_payload = {
            "timestamp": timestamp,
            "event_type": event_type,
            "details": details
        }
        
        # Gravação simples
        try:
            with self._open_with_retry('a') as f:
                f.write(json.dumps(event_payload, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"Error writing to log: {e}")
            
        return "" # Retorna string vazia para manter compatibilidade de assinatura se alguém esperar retorno
