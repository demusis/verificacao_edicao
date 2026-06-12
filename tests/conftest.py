"""Configuração compartilhada da suíte de testes."""
import sys
from pathlib import Path

import pytest

# Garante que o projeto seja importável quando o pytest rodar de qualquer cwd.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.case_manager import CaseManager  # noqa: E402


@pytest.fixture
def case_manager(tmp_path: Path) -> CaseManager:
    """CaseManager isolado em diretório temporário, já inicializado."""
    cm = CaseManager("caso_teste", base_dir=tmp_path)
    cm.setup()
    return cm
