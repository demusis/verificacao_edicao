import os
from pathlib import Path
import json

base_dir = Path(r"G:\Meu Drive\Em processamento\verificacao_edicao\cases")
if not base_dir.exists():
    print(f"Base dir {base_dir} not found.")
else:
    for case_folder in base_dir.iterdir():
        if not case_folder.is_dir(): continue
        
        manifest_path = case_folder / "results" / "batch_manifest.json"
        if manifest_path.exists():
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                
                report_dir = case_folder / "report"
                pdf_count = len(list(report_dir.glob("relatorio_*.pdf")))
                
                print(f"--- {case_folder.name} ---")
                print(f"  Analizados: {len(manifest)}")
                print(f"  PDFs: {pdf_count}")
                
                if len(manifest) != pdf_count:
                    print("  ❌ DISCREPÂNCIA!")
                    for idx, entry in enumerate(manifest):
                        fname = entry.get('filename')
                        stem = Path(fname).stem
                        pdf_file = report_dir / f"relatorio_{idx+1:02d}_{stem}.pdf"
                        if not pdf_file.exists():
                             print(f"  >> FALTANDO: [{idx+1}] {fname}")
            except Exception as e:
                print(f"  Erro ao ler {case_folder.name}: {e}")
