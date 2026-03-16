import json
import re
from pathlib import Path

def reconstruct_manifest(results_dir: Path):
    print(f"Buscando arquivos na pasta: {results_dir}")
    if not results_dir.exists():
        print("Pasta não encontrada.")
        return
        
    # Agrupar arquivos por prefixo (ex: '01', '02')
    # O prefixo é: f"{idx+1:02d}_{input_file.stem}" e depois "_module.json"
    # Entao arquivos tem padrão: 01_nomedoarquivo_module.json
    
    # Para saber o "nomedoarquivo", procuramos por *_file_analysis.json pois ele
    # guarda o filename original no seu conteúdo
    
    entries = {} # Mapeia prefixo -> dict de entry
    
    for json_file in results_dir.glob("*.json"):
        if json_file.name == "batch_manifest.json" or json_file.name == "prnu_matrix.json":
            continue
            
        # Tenta extrair o modulo final do nome
        # Nomes comuns: _file_analysis, _continuity, _compression, _prnu, 
        # _structure, _quantization, _image_forensics, _deepfake_analysis,
        # _audio_analysis, _audio_deepfake
        
        known_modules = [
            "file_analysis", "continuity", "compression", "prnu", "prnu_analysis",
            "structure", "quantization", "image_forensics", "deepfake_analysis",
            "audio_analysis", "audio_deepfake"
        ]
        
        module_type = None
        for mod in known_modules:
            if json_file.name.endswith(f"_{mod}.json"):
                module_type = mod
                break
                
        if not module_type:
            continue
            
        # O prefixo base é o nome sem o `_{module_type}.json`
        base_prefix = json_file.name[:-len(f"_{module_type}.json")]
        
        if base_prefix not in entries:
            entries[base_prefix] = {
                "base_prefix": base_prefix,
                "analysis_files": {}
            }
            
        entries[base_prefix]["analysis_files"][module_type] = json_file.name
        
        # Se for file_analysis, abrir pra extrair o nome real do arquivo submetido
        if module_type == "file_analysis":
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # No file_analysis.json, root tem file_info -> file_path
                    if "file_info" in data and "file_path" in data["file_info"]:
                        original_path = Path(data["file_info"]["file_path"]).name
                        entries[base_prefix]["filename"] = original_path
            except Exception as e:
                print(f"Erro lendo {json_file.name}: {e}")
                
    # Agora construimos a lista do manifest
    manifest_list = []
    
    # Ordenar por prefixo (que contem o id numérico ex: 01_xxx)
    sorted_keys = sorted(list(entries.keys()))
        
    for k in sorted_keys:
        d = entries[k]
        
        # Se não achamos o filename via file_analysis, deduzimos do prefixo tirando os números iniciais
        filename = d.get("filename")
        if not filename:
            m = re.match(r'^\d+_(.*?)$', k)
            filename = m.group(1) if m else k
            
        thumb_name = f"thumb_{Path(filename).stem}.jpg"
        if not (results_dir / thumb_name).exists():
            thumb_name = None
            
        manifest_entry = {
            "filename": filename,
            "thumbnail": thumb_name,
            "analysis_files": d["analysis_files"]
        }
        manifest_list.append(manifest_entry)
        
    print(f"Reconstruídos {len(manifest_list)} registros.")
    
    manifest_path = results_dir / "batch_manifest.json"
    with open(manifest_path, 'w', encoding='utf-8') as mf:
        json.dump(manifest_list, mf, indent=2, ensure_ascii=False)
        
    print(f"SALVO. Você pode agora cancelar o script anterior e reiniciar em Resume-mode!")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        reconstruct_manifest(path)
    else:
        # Prompt user
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        folder_selected = filedialog.askdirectory(title="Selecione a pasta 'resultados_nomedocaso' que está sendo processada agora")
        if folder_selected:
            reconstruct_manifest(Path(folder_selected))
