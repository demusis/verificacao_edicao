import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from datetime import timezone, timedelta

# Informações da Aplicação
APP_NAME = "ForensicVideoAnalyzer"
APP_VERSION = "0.1.0"

# Configurações de Diretório
BASE_DIR = Path(__file__).resolve().parent.parent
CASES_DIR = BASE_DIR / "cases"

# Configurações Regionais
try:
    TIMEZONE = ZoneInfo("America/Sao_Paulo")
except (ZoneInfoNotFoundError, ImportError):
    # Fallback para offset fixo de -3h (Horário Padrão de Brasília) se tzdata não disponível
    TIMEZONE = timezone(timedelta(hours=-3), name="America/Sao_Paulo")

DATE_FORMAT = "%d/%m/%Y"
TIME_FORMAT = "%H:%M:%S"
DATETIME_FORMAT = f"{DATE_FORMAT} {TIME_FORMAT}"

# Configurações de Log
LOG_FORMAT = "%(message)s"  # Logs serão estruturados em JSON no logger customizado

# Configurações de Análise
DEFAULT_SAMPLE_RATE = 10  # Analisar 1 a cada N frames
CHUNK_SIZE_MB = 10      # Tamanho do chunk de leitura de arquivo (em MB)
