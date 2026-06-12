import os
from pathlib import Path
import json

root = Path(r"G:\Meu Drive\Em processamento")
manifests = sorted(root.rglob("batch_manifest.json"), key=os.path.getmtime, reverse=True)

if not manifests:
    print("Nenhum manifesto encontrado.")
else:
    for m_path in manifests[:3]:  # Top 3 most recent
        results_dir = m_path.parent
        case_dir = results_dir.parent
        report_dir = case_dir / "report"
        
        if not report_dir.exists():
            continue
            
        with open(m_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
            
        pdfs = list(report_dir.glob("relatorio_*.pdf"))
        
        print(f"--- Caso: {case_dir.name} ---")
        print(f"Manifesto: {len(manifest)} arquivos")
        print(f"Report: {len(pdfs)} PDFs")
        
        if len(manifest) != len(pdfs):
            print(f"❌ DISCREPÂNCIA ENCONTRADA")
            # Encontrar qual está faltando
            for idx, entry in enumerate(manifest):
                fname = entry.get('filename')
                stem = Path(fname).stem
                pdf_p = report_dir / f"relatorio_{idx+1:02d}_{stem}.pdf"
                if not pdf_p.exists():
                    print(f"   ARQUIVO FALTANTE: Index {idx+1} - {fname}")
                    print(f"   Caminho esperado: {pdf_p}")
        else:
            print("✅ Contagem igual.")
