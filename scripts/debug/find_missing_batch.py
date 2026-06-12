import os
from pathlib import Path
import json

def scan_for_manifests(root_dir):
    for root, dirs, files in os.walk(root_dir):
        if 'batch_manifest.json' in files:
            manifest_path = Path(root) / 'batch_manifest.json'
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                
                if len(manifest) >= 30: # Procurando por lotes grandes
                    case_dir = manifest_path.parent.parent
                    report_dir = case_dir / 'report'
                    
                    if report_dir.exists():
                        pdfs = list(report_dir.glob('relatorio_*.pdf'))
                        print(f"CASE_FOUND: {case_dir} | Manifest: {len(manifest)} | PDFs: {len(pdfs)}")
                        
                        if len(manifest) != len(pdfs):
                            for idx, entry in enumerate(manifest):
                                fname = entry.get('filename')
                                stem = Path(fname).stem
                                # Check if PDF exists
                                pdf_pattern = f"relatorio_{idx+1:02d}_{stem}.pdf"
                                pdf_path = report_dir / pdf_pattern
                                if not pdf_path.exists():
                                    print(f"MISSING_PDF: [{idx+1}] {fname}")
            except Exception as e:
                pass

scan_for_manifests(r"G:\Meu Drive\Em processamento")
