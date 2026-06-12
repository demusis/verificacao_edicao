# Scripts auxiliares

Utilitários de manutenção e depuração que **não fazem parte do pipeline de produção**.

| Script | Propósito |
|--------|-----------|
| `download_deps.py` | Baixa wheels para instalação offline (salva em `vendor/wheels/`). |

## `debug/` — Depuração e QA manual

Scripts ad-hoc usados durante o desenvolvimento para investigar problemas.
Executar a partir da **raiz do projeto** (eles importam `core`/`modules`):

```bash
python scripts/debug/scan_cases.py
```

| Script | Propósito |
|--------|-----------|
| `debug_repro_full.py` | Reproduz o `FileAnalysisModule` em um arquivo específico. |
| `scan_cases.py` | Compara manifesto vs PDFs gerados em `cases/` (QA de lote). |
| `find_missing_pdfs.py` / `_v2.py` | Localiza relatórios faltantes em relação ao manifesto. |
| `find_missing_batch.py` / `find_large_batch.py` | Diagnóstico de lotes incompletos/grandes. |
| `scan_manifest_counts.py` | Conta entradas em `batch_manifest.json`. |
| `find_debug_data.py` | Localiza dados de depuração em casos. |
| `verify_audio_hash.py` | Valida hash de stream de áudio + relatório. |
| `verify_legend_dynamic.py` | Valida geração de legenda dinâmica nos relatórios. |
| `test_librosa_load.py` | Valida carregamento de áudio com librosa. |
| `test_reporting_standalone.py` | Testa o `ReportingModule` isolado. |

> **Nota:** a cobertura automatizada vive em `tests/` (pytest). Prefira escrever
> um teste lá em vez de adicionar novos scripts aqui.
