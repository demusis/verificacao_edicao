import os
from pathlib import Path
import json

root = Path(r"G:\Meu Drive\Em processamento")

for m_path in root.rglob("batch_manifest.json"):
    try:
        with open(m_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        
        if len(manifest) >= 40: # Procura lotes grandes
            results_dir = m_path.parent
            case_dir = results_dir.parent
            report_dir = case_dir / "report"
            
            pdfs = list(report_dir.glob("relatorio_*.pdf"))
            print(f"Lote encontrado: {case_dir.name} ({len(manifest)} arquivos)")
            
            missing_indices = []
            for idx, entry in enumerate(manifest):
                fname = entry.get('filename')
                stem = Path(fname).stem
                pdf_p = report_dir / f"relatorio_{idx+1:02d}_{stem}.pdf"
                if not pdf_p.exists():
                    missing_indices.append((idx+1, fname))
            
            if missing_indices:
                print(f"❌ FALTAM {len(missing_indices)} PDFs:")
                for i, f in missing_indices:
                    print(f"   [{i}] {f}")
            else:
                print("✅ Todos os PDFs presentes.")
    except:
        continue
