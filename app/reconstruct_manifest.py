import json
import re
from pathlib import Path


def reconstruct_manifest(results_dir: Path):
    print(f"Buscando arquivos na pasta: {results_dir}")
    if not results_dir.exists():
        print("Pasta não encontrada.")
        return
        
    entries = {} # Mapeia prefixo -> dict de entry
    
    known_modules = [
        "file_analysis", "continuity", "compression", "prnu", "prnu_analysis",
        "structure", "quantization", "image_forensics", "deepfake_analysis",
        "audio_analysis", "audio_deepfake"
    ]
    
    # Primeiro, listar todos os arquivos JSON e agrupar por prefixo base
    json_files = list(results_dir.glob("*.json"))
    for json_file in json_files:
        if json_file.name in ["batch_manifest.json", "prnu_matrix.json"]:
            continue
            
        module_type = None
        for mod in known_modules:
            if json_file.name.endswith(f"_{mod}.json"):
                module_type = mod
                break
                
        if not module_type:
            continue
            
        base_prefix = json_file.name[:-len(f"_{module_type}.json")]
        
        if base_prefix not in entries:
            entries[base_prefix] = {
                "base_prefix": base_prefix,
                "analysis_files": {}
            }
            
        entries[base_prefix]["analysis_files"][module_type] = json_file.name

    # Construir lista e tentar identificar nomes de arquivos reais
    manifest_list = []
    
    # Ordenar por prefixo
    sorted_prefixes = sorted(entries.keys())
    
    for prefix in sorted_prefixes:
        data = entries[prefix]
        
        # Tentar extrair nome original do file_analysis
        found_filename = None
        fa_file = data["analysis_files"].get("file_analysis")
        if fa_file:
            try:
                with open(results_dir / fa_file, encoding='utf-8') as f:
                    fa_data = json.load(f)
                    # Tentar vários campos possíveis de metadados
                    fmt = fa_data.get("metadata", {}).get("format", {})
                    if "filename" in fmt:
                        found_filename = Path(fmt["filename"]).name
            except Exception:
                pass
        
        # Fallback: Tirar o prefixo numérico (ex: 01_nomedoarquivo -> nomedoarquivo)
        if not found_filename:
            # Padrão: 01_NomeDoArquivo
            m = re.match(r'^\d+_(.*)$', prefix)
            found_filename = m.group(1) if m else prefix
        
        # Se o filename ainda parece um thumb ou algo errado, limpar
        if found_filename.startswith("thumb_"):
             # Provavelmente é um prefixo de erro ou thumb gerado incorretamente
             continue

        # Validar se temos pelo menos uma análise mínima (file_analysis) para considerar pronto
        if "file_analysis" not in data["analysis_files"]:
            continue

        thumb_name = f"thumb_{Path(found_filename).stem}.jpg"
        if not (results_dir / thumb_name).exists():
            thumb_name = None
            
        manifest_entry = {
            "filename": found_filename,
            "thumbnail": thumb_name,
            "analysis_files": data["analysis_files"]
        }
        manifest_list.append(manifest_entry)
        
    print(f"Reconstruídos {len(manifest_list)} registros.")
    
    manifest_path = results_dir / "batch_manifest.json"
    with open(manifest_path, 'w', encoding='utf-8') as mf:
        json.dump(manifest_list, mf, indent=2, ensure_ascii=False)
        
    print(f"SALVO. Manifesto com {len(manifest_list)} entradas gerado em {manifest_path}")

if __name__ == "__main__":
    results_path = Path("D:/CFTV-SINOP/analise_2/analise_2/results")
    reconstruct_manifest(results_path)
