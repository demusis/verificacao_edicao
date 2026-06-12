"""
Interface de Linha de Comando (CLI) para Análise Forense.

Este módulo fornece uma interface CLI usando Typer para executar
o pipeline completo de análise forense em arquivos de vídeo e imagem.

Exemplo de uso:
    python -m app.cli "video.mp4" --case-name "Caso_001"
    python -m app.cli "imagem.jpg" --deepfake-fast
"""
import json
import logging
import os
import sys
from pathlib import Path

import typer

# Permitir execução direta sem -m
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.case_manager import CaseManager
from core.config_schema import AnalysisConfig
from modules.compression_analysis import CompressionAnalysisModule
from modules.continuity import ContinuityModule
from modules.deepfake_analysis import DeepfakeAnalysisModule
from modules.file_analysis import FileAnalysisModule
from modules.image_forensics import ImageForensicsModule
from modules.prnu_analysis import PrnuAnalysisModule
from modules.quantization_analysis import QuantizationAnalysisModule
from modules.reporting import ReportingModule
from modules.structure_analysis import StructureAnalysisModule

# Configurar logging básico
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
_logger = logging.getLogger(__name__)

app = typer.Typer(
    help="Ferramenta de Análise Forense de Vídeo e Imagem - CLI",
    add_completion=False
)

# Extensões de vídeo suportadas
VIDEO_EXTENSIONS = frozenset(['.mp4', '.avi', '.mov', '.mkv', '.webm', '.m4v'])


def _is_video(file_path: Path) -> bool:
    """Verifica se o arquivo é um vídeo baseado na extensão."""
    return file_path.suffix.lower() in VIDEO_EXTENSIONS


def _run_module(
    name: str,
    module_instance: object,
    input_file: Path,
    **kwargs
) -> bool:
    """Executa um módulo de análise com tratamento de erros.
    
    Args:
        name: Nome do módulo para exibição.
        module_instance: Instância do módulo a executar.
        input_file: Arquivo de entrada.
        **kwargs: Argumentos adicionais para module.run().
        
    Returns:
        True se executou com sucesso, False caso contrário.
    """
    try:
        typer.secho(f"Executando {name}...", fg=typer.colors.BLUE)
        module_instance.run(input_file, **kwargs)
        typer.secho(f"{name} Concluída.", fg=typer.colors.GREEN)
        return True
    except Exception as e:
        typer.secho(f"Falha na {name}: {e}", fg=typer.colors.RED)
        _logger.exception("Erro no módulo %s", name)
        return False


@app.command()
def analyze(
    input_file: Path = typer.Argument(
        ...,
        help="Caminho do arquivo para análise",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True
    ),
    case_name: str | None = typer.Option(
        None,
        help="Nome do caso. Se omitido, será gerado automaticamente."
    ),
    threshold: float = typer.Option(
        0.3,
        help="Limiar de detecção de cortes (0.0 a 1.0)."
    ),
    # Deepfake Configs
    df_noise: int = typer.Option(
        50,
        "--deepfake-noise",
        help="Susceptibilidade a Ruído (10-90%)."
    ),
    df_jitter: int = typer.Option(
        15,
        "--deepfake-jitter",
        help="Sensibilidade de Jitter para vídeos (5-50)."
    ),
    df_fast: bool = typer.Option(
        False,
        "--deepfake-fast",
        help="Ativar Modo Rápido (pula FFT/LBP em cada frame)."
    )
) -> None:
    """Executa o pipeline completo de análise forense (Imagem ou Vídeo)."""
    
    # 1. Preparar Configuração
    config = AnalysisConfig(
        deepfake_noise_threshold=df_noise,
        deepfake_jitter_threshold=df_jitter,
        deepfake_fast_mode=df_fast,
        scene_threshold=threshold,
    )
    
    if not case_name:
        case_name = f"case_{input_file.stem}"
    
    typer.echo(f"Iniciando análise para o caso: {case_name}")
    typer.echo(f"Arquivo de entrada: {input_file}")
    
    # 2. Setup
    try:
        cm = CaseManager(case_name)
        cm.setup()
        logger = cm.get_logger()
        logger.log("CLI_START", {"input_file": str(input_file)})
    except Exception as e:
        typer.secho(f"Erro crítico na inicialização: {e}", fg=typer.colors.RED)
        raise typer.Exit(1) from e
    
    prefix = f"01_{input_file.stem}"
    is_video = _is_video(input_file)
    
    # 3. Pipeline Execution
    
    # Comum: Análise de Arquivo
    file_mod = FileAnalysisModule(cm)
    _run_module(
        "Análise de Arquivo (Metadata)",
        file_mod,
        input_file,
        output_filename=f"{prefix}_file_analysis.json"
    )
    
    if is_video:
        # === FLUXO DE VÍDEO ===
        
        cont_mod = ContinuityModule(cm)
        _run_module(
            "Análise de Continuidade",
            cont_mod,
            input_file,
            threshold=config.scene_threshold,
            output_filename=f"{prefix}_continuity.json"
        )
        
        struct_mod = StructureAnalysisModule(cm)
        _run_module(
            "Mapeamento de Estrutura",
            struct_mod,
            input_file,
            output_filename=f"{prefix}_structure.json"
        )
        
        comp_mod = CompressionAnalysisModule(cm)
        _run_module(
            "Análise de Compressão",
            comp_mod,
            input_file,
            output_filename=f"{prefix}_compression.json"
        )
        
        quant_mod = QuantizationAnalysisModule(cm)
        _run_module(
            "Análise de Quantização",
            quant_mod,
            input_file,
            output_filename=f"{prefix}_quantization.json"
        )
        
        # PRNU
        try:
            typer.secho("Executando Análise PRNU...", fg=typer.colors.BLUE)
            prnu_mod = PrnuAnalysisModule(cm)
            prnu_mod.frame_limit = config.prnu_frame_limit
            prnu_mod.run(input_file, output_filename=f"{prefix}_prnu.json")
            typer.secho("PRNU Concluída.", fg=typer.colors.GREEN)
        except Exception as e:
            typer.secho(f"Falha na PRNU: {e}", fg=typer.colors.RED)
            _logger.exception("Erro no módulo PRNU")
        
        # Deepfake Vídeo
        try:
            typer.secho("Executando Deepfake Analysis (Vídeo)...", fg=typer.colors.BLUE)
            df_mod = DeepfakeAnalysisModule(config=config.to_dict())
            df_res = df_mod.run_video(input_file)
            
            output_path = cm.results_dir / f"{prefix}_deepfake_analysis.json"
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(df_res, f, indent=4, ensure_ascii=False)
            typer.secho("Deepfake Analysis Concluída.", fg=typer.colors.GREEN)
        except Exception as e:
            typer.secho(f"Falha na Deepfake Analysis: {e}", fg=typer.colors.RED)
            _logger.exception("Erro no módulo Deepfake (vídeo)")
    
    else:
        # === FLUXO DE IMAGEM ===
        
        img_mod = ImageForensicsModule(cm, config=config.to_dict())
        _run_module(
            "Análise Forense de Imagem",
            img_mod,
            input_file,
            output_filename=f"{prefix}_image_analysis.json"
        )
        
        # Deepfake Imagem
        try:
            typer.secho("Executando Deepfake Analysis (Imagem)...", fg=typer.colors.BLUE)
            df_mod = DeepfakeAnalysisModule(config=config.to_dict())
            df_res = df_mod.run_image(input_file)
            
            output_path = cm.results_dir / f"{prefix}_deepfake_analysis.json"
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(df_res, f, indent=4, ensure_ascii=False)
            typer.secho("Deepfake Analysis Concluída.", fg=typer.colors.GREEN)
        except Exception as e:
            typer.secho(f"Falha na Deepfake Analysis: {e}", fg=typer.colors.RED)
            _logger.exception("Erro no módulo Deepfake (imagem)")
    
    # 4. Reporting
    try:
        typer.secho("Gerando Relatório...", fg=typer.colors.BLUE)
        report_mod = ReportingModule(cm)
        report_mod.generate()
        typer.secho(f"Relatório gerado em: {cm.report_dir}", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Falha na Geração de Relatório: {e}", fg=typer.colors.RED)
        _logger.exception("Erro na geração de relatório")
    
    typer.echo("Processo finalizado.")


if __name__ == "__main__":
    app()
