from pathlib import Path
from typing import Optional
from .config import CASES_DIR
from .logger import Logger

class CaseManager:
    """Gerenciador de estrutura de diretórios e logs por caso."""
    
    def __init__(self, case_name: str, base_dir: Path = CASES_DIR):
        self.case_name = case_name
        self.case_dir = Path(base_dir) / case_name
        
        # Subdiretórios
        self.results_dir = self.case_dir / "results"
        self.report_dir = self.case_dir / "report"
        
        self.log_path = self.case_dir / "execution.log"
        self.evidence_manifest_path = self.case_dir / "evidence_manifest.json"
        
        self.logger: Optional[Logger] = None

    def setup(self) -> Logger:
        """Cria estrutura de pastas e inicializa o logger."""
        self.case_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(exist_ok=True)
        self.report_dir.mkdir(exist_ok=True)
        
        self.logger = Logger(self.log_path)
        
        # Log inicial
        self.logger.log("CASE_SETUP", {
            "case_name": self.case_name,
            "case_dir": str(self.case_dir),
            "status": "Initialized"
        })
        
        return self.logger

    def get_logger(self) -> Logger:
        """Retorna o logger, inicializando se necessário."""
        if not self.logger:
            return self.setup()
        return self.logger
