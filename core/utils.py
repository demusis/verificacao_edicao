from datetime import datetime
from .config import TIMEZONE, DATETIME_FORMAT

def get_current_timestamp() -> datetime:
    """Retorna o timestamp atual com timezone do sistema."""
    return datetime.now().astimezone()

def format_timestamp(dt: datetime) -> str:
    """Formata o datetime para string no padrão pt-BR."""
    return dt.strftime(DATETIME_FORMAT)

def get_timestamp_iso(dt: datetime = None) -> str:
    """Retorna timestamp em formato ISO 8601 (string)."""
    if dt is None:
        dt = get_current_timestamp()
    return dt.isoformat()
