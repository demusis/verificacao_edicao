import typer
from pathlib import Path
from typing import Optional
import sys
import os
import json

# Permitir execução direta sem -m
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.case_manager import CaseManager
from modules.file_analysis import FileAnalysisModule
from modules.continuity import ContinuityModule
from modules.compression_analysis import CompressionAnalysisModule
from modules.prnu_analysis import PrnuAnalysisModule
from modules.quantization_analysis import QuantizationAnalysisModule
from modules.structure_analysis import StructureAnalysisModule
from modules.image_analysis import ImageForensicsModule
from modules.deepfake_analysis import DeepfakeAnalysisModule
from modules.reporting import ReportingModule

app = typer.Typer(help="Ferramenta de Análise Forense de Vídeo e Imagem - CLI")

@app.command()
def analyze(
    input_file: Path = typer.Argument(..., help="Caminho do arquivo para análise", exists=True, file_okay=True, dir_okay=False, resolve_path=True),
    case_name: Optional[str] = typer.Option(None, help="Nome do caso. Se omitido, será gerado automaticamente."),
    threshold: float = typer.Option(0.3, help="Limiar de detecção de cortes (0.0 a 1.0)."),
    
    # Deepfake Configs
    df_noise: int = typer.Option(50, "--deepfake-noise", help="Susceptibilidade a Ruído (10-90%)."),
    df_jitter: int = typer.Option(15, "--deepfake-jitter", help="Sensibilidade de Jitter para vídeos (5-50)."),
    df_fast: bool = typer.Option(False, "--deepfake-fast", help="Ativar Modo Rápido (pula FFT/LBP em cada frame).")
):
    """Executa o pipeline completo de análise forense (Imagem ou Vídeo)."""
    
    # 1. Preparar Configuração
    config = {
        "deepfake_noise_threshold": df_noise,
        "deepfake_jitter_threshold": df_jitter,
        "deepfake_fast_mode": df_fast,
        "copymove_features": 2000,
        "copymove_min_cluster": 4,
        "resampling_block_size": 64,
        "ela_quality": 90,
        "prnu_frame_limit": 50
    }

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
        raise typer.Exit(1)
    
    prefix = f"01_{input_file.stem}"
    is_video = input_file.suffix.lower() in ['.mp4', '.avi', '.mov', '.mkv']
    
    # Helper for running modules
    def run_module(name, module_cls, **kwargs):
        try:
            typer.secho(f"Executando {name}...", fg=typer.colors.BLUE)
            mod = module_cls(cm, config=config) if 'config' in module_cls.__init__.__code__.co_varnames else module_cls(cm)
            
            # Alguns módulos usam config no init, outros não. 
            # Ajuste dinâmico ou fixo: ImageForensics e Deepfake aceitam config.
            
            mod.run(input_file, **kwargs)
            typer.secho(f"{name} Concluída.", fg=typer.colors.GREEN)
            return True
        except Exception as e:
            typer.secho(f"Falha na {name}: {e}", fg=typer.colors.RED)
            return False

    # 3. Pipeline Execution
    
    # Comum: Análise de Arquivo
    run_module("Análise de Arquivo (Metadata)", FileAnalysisModule, output_filename=f"{prefix}_file_analysis.json")

    if is_video:
        # === FLUXO DE VÍDEO ===
        run_module("Análise de Continuidade", ContinuityModule, threshold=threshold, output_filename=f"{prefix}_continuity.json")
        run_module("Mapeamento de Estrutura", StructureAnalysisModule, output_filename=f"{prefix}_structure.json")
        run_module("Análise de Compressão", CompressionAnalysisModule, output_filename=f"{prefix}_compression.json")
        run_module("Análise de Quantização", QuantizationAnalysisModule, output_filename=f"{prefix}_quantization.json")
        
        # PRNU
        try:
            typer.secho("Executando Análise PRNU...", fg=typer.colors.BLUE)
            prnu_mod = PrnuAnalysisModule(cm)
            prnu_mod.frame_limit = config['prnu_frame_limit']
            prnu_mod.run(input_file, output_filename=f"{prefix}_prnu.json")
            typer.secho("PRNU Concluída.", fg=typer.colors.GREEN)
        except Exception as e:
            typer.secho(f"Falha na PRNU: {e}", fg=typer.colors.RED)

        # Deepfake Vídeo
        try:
            typer.secho("Executando Deepfake Analysis (Vídeo)...", fg=typer.colors.BLUE)
            df_res = DeepfakeAnalysisModule(config=config).run_video(input_file)
            with open(cm.results_dir / f"{prefix}_deepfake_analysis.json", 'w', encoding='utf-8') as f:
                json.dump(df_res, f, indent=4)
            typer.secho("Deepfake Analysis Concluída.", fg=typer.colors.GREEN)
        except Exception as e:
            typer.secho(f"Falha na Deepfake Analysis: {e}", fg=typer.colors.RED)

    else:
        # === FLUXO DE IMAGEM ===
        run_module("Análise Forense de Imagem", ImageForensicsModule, output_filename=f"{prefix}_image_analysis.json")
        
        # Deepfake Imagem
        try:
            typer.secho("Executando Deepfake Analysis (Imagem)...", fg=typer.colors.BLUE)
            df_res = DeepfakeAnalysisModule(config=config).run_image(input_file)
            with open(cm.results_dir / f"{prefix}_deepfake_analysis.json", 'w', encoding='utf-8') as f:
                json.dump(df_res, f, indent=4)
            typer.secho("Deepfake Analysis Concluída.", fg=typer.colors.GREEN)
        except Exception as e:
            typer.secho(f"Falha na Deepfake Analysis: {e}", fg=typer.colors.RED)

    # 4. Reporting
    try:
        typer.secho("Gerando Relatório...", fg=typer.colors.BLUE)
        report_mod = ReportingModule(cm)
        report_mod.generate()
        typer.secho(f"Relatório gerado em: {cm.report_dir}", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Falha na Geração de Relatório: {e}", fg=typer.colors.RED)

    typer.echo("Processo finalizado.")

if __name__ == "__main__":
    app()
