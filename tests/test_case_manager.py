"""Testes para core.case_manager (estrutura de diretórios por caso)."""
from pathlib import Path

from core.case_manager import CaseManager


def test_setup_creates_directory_structure(tmp_path: Path) -> None:
    cm = CaseManager("caso_001", base_dir=tmp_path)
    cm.setup()

    assert cm.case_dir.is_dir()
    assert cm.results_dir.is_dir()
    assert cm.report_dir.is_dir()


def test_setup_logs_case_setup_event(tmp_path: Path) -> None:
    cm = CaseManager("caso_001", base_dir=tmp_path)
    logger = cm.setup()

    events = logger.read_events()
    assert events[0]["event_type"] == "CASE_SETUP"
    assert events[0]["details"]["case_name"] == "caso_001"


def test_case_name_is_sanitized(tmp_path: Path) -> None:
    cm = CaseManager("  caso_com_espacos.. ", base_dir=tmp_path)

    assert cm.case_name == "caso_com_espacos"
    assert cm.case_dir.name == "caso_com_espacos"


def test_get_logger_initializes_lazily(tmp_path: Path) -> None:
    cm = CaseManager("caso_lazy", base_dir=tmp_path)
    assert cm.logger is None

    logger = cm.get_logger()
    assert logger is not None
    assert cm.case_dir.is_dir()


def test_get_logger_returns_same_instance(tmp_path: Path) -> None:
    cm = CaseManager("caso_singleton", base_dir=tmp_path)

    assert cm.get_logger() is cm.get_logger()


def test_setup_is_idempotent(tmp_path: Path) -> None:
    cm = CaseManager("caso_repetido", base_dir=tmp_path)
    cm.setup()
    cm.setup()  # não deve lançar com diretórios já existentes

    assert cm.case_dir.is_dir()
