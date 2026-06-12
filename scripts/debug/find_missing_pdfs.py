import json
from pathlib import Path

# Pasta do caso (ajustar conforme necessário ou rodar na raiz do caso)
results_dir = Path(r"g:\Meu Drive\Em processamento\verificacao_edicao\cases\final_test\results")
report_dir = Path(r"g:\Meu Drive\Em processamento\verificacao_edicao\cases\final_test\report")

manifest_path = results_dir / "batch_manifest.json"

if not manifest_path.exists():
    print("Manifesto não encontrado.")
else:
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    print(f"Arquivos no Manifesto: {len(manifest)}")
    
    missing = []
    for idx, entry in enumerate(manifest):
        filename = entry.get('filename')
        stem = Path(filename).stem
        # O padrão atual é relatorio_XX_stem.pdf
        pdf_name = f"relatorio_{idx+1:02d}_{stem}.pdf"
        pdf_path = report_dir / pdf_name
        
        if not pdf_path.exists():
            missing.append((idx+1, filename, pdf_name))
            
    if not missing:
        print("✅ Todos os PDFs estão presentes conforme o índice do manifesto atual.")
    else:
        print(f"❌ Faltam {len(missing)} PDFs:")
        for idx, fname, pname in missing:
            print(f"  - [{idx}] {fname} -> Esperado: {pname}")
