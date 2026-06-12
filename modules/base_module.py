"""
Classe base abstrata para módulos de análise forense.

Este módulo define a interface padrão que todos os módulos de análise
devem implementar, garantindo consistência e facilidade de manutenção.
"""
import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.case_manager import CaseManager
from core.config_schema import AnalysisConfig

_logger = logging.getLogger(__name__)


class BaseAnalysisModule(ABC):
    """Interface base para todos os módulos de análise forense.
    
    Esta classe abstrata define o contrato que todos os módulos de análise
    devem seguir, incluindo métodos de logging padronizados e gerenciamento
    de configuração.
    
    Attributes:
        MODULE_NAME: Nome do módulo para identificação em logs.
        cm: Instância do CaseManager para gerenciar diretórios.
        config: Configuração de análise.
        logger: Logger do case manager para auditoria.
    
    Example:
        >>> class MyModule(BaseAnalysisModule):
        ...     MODULE_NAME = "MeuModulo"
        ...     
        ...     def run(self, input_file, output_filename, progress_callback=None):
        ...         self._log_start(input_file)
        ...         # ... fazer análise ...
        ...         self._save_results(result, output_filename)
        ...         return result
    """
    
    MODULE_NAME: str = "BaseModule"
    
    def __init__(
        self,
        case_manager: CaseManager,
        config: AnalysisConfig | None = None
    ) -> None:
        """Inicializa o módulo de análise.
        
        Args:
            case_manager: Gerenciador de caso para diretórios e logs.
            config: Configuração opcional. Se None, usa padrões.
        """
        self.cm = case_manager
        self.config = config or AnalysisConfig()
        self.logger = self.cm.get_logger()
    
    @abstractmethod
    def run(
        self,
        input_file: Path,
        output_filename: str = "analysis.json",
        progress_callback: Callable[[str], None] | None = None
    ) -> dict[str, Any]:
        """Executa a análise no arquivo de entrada.
        
        Args:
            input_file: Caminho do arquivo a ser analisado.
            output_filename: Nome do arquivo de saída (relativo a results_dir).
            progress_callback: Função opcional para reportar progresso.
            
        Returns:
            Dicionário com os resultados da análise.
            
        Raises:
            FileNotFoundError: Se o arquivo de entrada não existir.
            RuntimeError: Se ocorrer erro durante a análise.
        """
        pass
    
    def _log_start(self, input_file: Path) -> None:
        """Registra início da execução do módulo.
        
        Args:
            input_file: Arquivo sendo analisado.
        """
        self.logger.log("START_MODULE", {
            "module": self.MODULE_NAME,
            "file": str(input_file)
        })
    
    def _log_success(self, output_file: Path) -> None:
        """Registra conclusão bem-sucedida do módulo.
        
        Args:
            output_file: Arquivo de saída gerado.
        """
        self.logger.log("MODULE_SUCCESS", {
            "module": self.MODULE_NAME,
            "output": str(output_file)
        })
    
    def _log_error(self, error: Exception) -> None:
        """Registra erro na execução do módulo.
        
        Args:
            error: Exceção que ocorreu.
        """
        self.logger.log("MODULE_ERROR", {
            "module": self.MODULE_NAME,
            "error": str(error),
            "type": type(error).__name__
        })
        _logger.exception("Erro no módulo %s", self.MODULE_NAME)
    
    def _save_results(
        self,
        results: dict[str, Any],
        output_filename: str
    ) -> Path:
        """Salva resultados em arquivo JSON.
        
        Args:
            results: Dicionário de resultados.
            output_filename: Nome do arquivo de saída.
            
        Returns:
            Caminho completo do arquivo salvo.
        """
        output_path = self.cm.results_dir / output_filename
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        self._log_success(output_path)
        return output_path
    
    def _notify_progress(
        self,
        message: str,
        callback: Callable[[str], None] | None = None
    ) -> None:
        """Notifica progresso da análise.
        
        Args:
            message: Mensagem de progresso.
            callback: Função de callback opcional.
        """
        if callback:
            callback(message)
