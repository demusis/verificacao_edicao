"""
Logger para auditoria de eventos forenses.

Este módulo fornece um logger que grava eventos estruturados em JSON-Lines,
adequado para trilhas de auditoria em análises forenses.

Integridade (hash chain):
    Cada evento gravado contém ``prev_hash`` (hash do evento anterior) e
    ``event_hash`` (SHA-256 do próprio evento, incluindo ``prev_hash``).
    Isso encadeia criptograficamente os eventos: qualquer alteração, remoção
    ou inserção de uma linha intermediária quebra a verificação da cadeia.
    Use :meth:`Logger.verify_chain` (ou ``python -m tools.verify_audit_log``)
    para auditar um log existente.

    Logs gravados por versões anteriores (sem campos de hash) continuam
    legíveis: as linhas legadas são toleradas na verificação e reportadas
    como ``legacy_events``.
"""
import hashlib
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, TextIO

from .utils import get_timestamp_iso

_module_logger = logging.getLogger(__name__)

#: Hash usado como ``prev_hash`` do primeiro evento da cadeia.
GENESIS_HASH = "0" * 64


def _compute_event_hash(payload: dict[str, Any]) -> str:
    """Calcula o SHA-256 canônico de um evento (sem o campo ``event_hash``).

    A serialização usa chaves ordenadas e separadores fixos para que o
    hash seja determinístico independentemente da ordem de inserção.

    Args:
        payload: Evento contendo timestamp, event_type, details e prev_hash.

    Returns:
        Hash SHA-256 em hexadecimal.
    """
    hashable = {k: v for k, v in payload.items() if k != "event_hash"}
    canonical = json.dumps(
        hashable, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class Logger:
    """Logger estruturado para eventos forenses com cadeia de hashes.

    Grava eventos em formato JSON-Lines (JSONL) com timestamp, tipo de
    evento, detalhes e encadeamento criptográfico (``prev_hash`` /
    ``event_hash``). Implementa retry para lidar com file locking no
    Windows e é seguro para uso concorrente entre threads do mesmo
    processo.

    Attributes:
        log_path: Caminho do arquivo de log.
        MAX_RETRIES: Número máximo de tentativas de escrita.
        RETRY_DELAY: Intervalo entre tentativas (segundos).

    Example:
        >>> logger = Logger(Path("case/execution.log"))
        >>> logger.log("ANALYSIS_START", {"file": "video.mp4"})
        >>> logger.verify_chain()["valid"]
        True
    """

    MAX_RETRIES: int = 5
    RETRY_DELAY: float = 0.1

    def __init__(self, log_path: Path) -> None:
        """Inicializa o logger.

        Args:
            log_path: Caminho para o arquivo de log.
        """
        self.log_path = Path(log_path)
        self._write_lock = threading.Lock()
        self._ensure_log_file()
        self._last_hash = self._load_last_hash()

    def _ensure_log_file(self) -> None:
        """Garante que o arquivo de log e diretório existam."""
        if not self.log_path.parent.exists():
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.touch()

    def _load_last_hash(self) -> str:
        """Recupera o hash do último evento gravado para retomar a cadeia.

        Linhas legadas (sem ``event_hash``) são ignoradas; se nenhum evento
        com hash existir, a cadeia parte do :data:`GENESIS_HASH`.

        Returns:
            Hash do último evento encadeado ou GENESIS_HASH.
        """
        for event in reversed(self.read_events()):
            event_hash = event.get("event_hash")
            if event_hash:
                return event_hash
        return GENESIS_HASH

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
        last_error: Exception | None = None

        for _attempt in range(self.MAX_RETRIES):
            try:
                return open(self.log_path, mode, encoding='utf-8')
            except (PermissionError, BlockingIOError) as e:
                last_error = e
                time.sleep(self.RETRY_DELAY)

        if last_error:
            raise last_error
        raise OSError("Could not open log file after retries")

    def log(
        self,
        event_type: str,
        details: dict[str, Any] | None = None
    ) -> None:
        """Registra um evento com timestamp, encadeado ao evento anterior.

        Args:
            event_type: Tipo do evento (ex: "START_MODULE", "ERROR").
            details: Dicionário com detalhes adicionais.
        """
        if details is None:
            details = {}

        with self._write_lock:
            event_payload = {
                "timestamp": get_timestamp_iso(),
                "event_type": event_type,
                "details": details,
                "prev_hash": self._last_hash,
            }
            event_payload["event_hash"] = _compute_event_hash(event_payload)

            try:
                with self._open_with_retry('a') as f:
                    f.write(json.dumps(event_payload, ensure_ascii=False) + "\n")
                # Só avança a cadeia se a escrita foi persistida, para que
                # o prev_hash em memória nunca aponte para um evento perdido.
                self._last_hash = event_payload["event_hash"]
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

    def verify_chain(self) -> dict[str, Any]:
        """Verifica a integridade da cadeia de hashes do log.

        Para cada evento com campos de hash, confere que:
        1. ``event_hash`` corresponde ao conteúdo do evento (não alterado);
        2. ``prev_hash`` corresponde ao ``event_hash`` do evento anterior
           (nenhum evento removido, inserido ou reordenado).

        Eventos legados (sem ``event_hash``) são contabilizados em
        ``legacy_events`` e não invalidam a cadeia, mas a porção legada
        do log não tem garantia criptográfica.

        Returns:
            Dicionário com: ``valid`` (bool), ``total_events``,
            ``verified_events``, ``legacy_events`` e ``errors``
            (lista de ``{"index", "reason"}``).
        """
        events = self.read_events()
        errors: list[dict[str, Any]] = []
        verified = 0
        legacy = 0
        expected_prev = GENESIS_HASH

        for index, event in enumerate(events):
            stored_hash = event.get("event_hash")
            if not stored_hash:
                legacy += 1
                continue

            if event.get("prev_hash") != expected_prev:
                errors.append({
                    "index": index,
                    "reason": (
                        f"prev_hash não corresponde ao evento anterior "
                        f"(esperado {expected_prev[:12]}…, "
                        f"encontrado {str(event.get('prev_hash'))[:12]}…)"
                    ),
                })

            recomputed = _compute_event_hash(event)
            if recomputed != stored_hash:
                errors.append({
                    "index": index,
                    "reason": "event_hash não corresponde ao conteúdo (evento alterado)",
                })
            else:
                verified += 1

            expected_prev = stored_hash

        return {
            "valid": not errors,
            "total_events": len(events),
            "verified_events": verified,
            "legacy_events": legacy,
            "errors": errors,
        }
