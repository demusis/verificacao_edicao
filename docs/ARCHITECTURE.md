# Arquitetura — VerificacaoEdicao

Visão técnica do sistema para desenvolvedores. Para uso da ferramenta, veja o [README](../README.md).

## Visão geral

O sistema é organizado em **4 camadas**, com dependências fluindo de cima para baixo:

```
┌─────────────────────────────────────────────────┐
│  app/        Pontos de entrada                  │
│              gui.py (PySide6) · cli.py (Typer)  │
│              cluster_dashboard.py               │
├─────────────────────────────────────────────────┤
│  modules/    Módulos de análise forense         │
│              (um JSON de resultado por módulo)  │
├─────────────────────────────────────────────────┤
│  core/       Infraestrutura                     │
│              CaseManager · Logger · Hashing ·   │
│              AnalysisConfig                     │
├─────────────────────────────────────────────────┤
│  adapters/   Integrações externas               │
│              FFmpegAdapter (ffmpeg/ffprobe)     │
└─────────────────────────────────────────────────┘
```

## Fluxo de execução

1. O usuário seleciona arquivos via GUI (`app/gui.py`, worker em `QThread`) ou CLI (`app/cli.py`, síncrono).
2. `CaseManager.setup()` cria a estrutura do caso (`cases/<nome>/results/`, `report/`) e inicializa o `Logger` de auditoria.
3. Cada arquivo passa pelo **pipeline sequencial** de módulos. Cada módulo:
   - registra início/fim/erro no log de auditoria;
   - grava seu resultado como JSON independente em `results/`;
   - falha isoladamente sem derrubar o pipeline.
4. `ReportingModule` consolida todos os JSONs, gera `.tex` e compila com `pdflatex` para o laudo final em `report/`.

## Camada `core/`

| Arquivo | Responsabilidade |
|---------|------------------|
| `case_manager.py` | Estrutura de diretórios por caso; dono do `Logger`. |
| `logger.py` | Log de auditoria JSONL com **hash chain SHA-256** (ver abaixo). |
| `hashing.py` | SHA-512 de arquivo (em chunks) e de stream isolado via FFmpeg. |
| `config_schema.py` | `AnalysisConfig` (dataclass, ~50 parâmetros, serialização JSON). |
| `config.py` | Constantes globais, detecção de bundle PyInstaller, timezone. |
| `utils.py` | Utilitários de timestamp (pt-BR e ISO 8601). |

### Log de auditoria (hash chain)

Cada evento gravado em `execution.log` contém:

```json
{
  "timestamp": "...", "event_type": "...", "details": {},
  "prev_hash": "<event_hash do evento anterior>",
  "event_hash": "<SHA-256 canônico deste evento>"
}
```

O primeiro evento encadeia a partir de `GENESIS_HASH` (64 zeros). Qualquer
alteração, remoção, inserção ou reordenação de eventos quebra a cadeia.
Verificação:

```bash
python tools/verify_audit_log.py cases/case_X/execution.log
```

Logs gravados antes da introdução do hash chain permanecem legíveis e são
reportados como `legacy_events` na verificação (sem garantia criptográfica).

## Camada `modules/`

Todos os módulos expõem `run(input_file, output_filename, ...) -> dict` e gravam
seu JSON em `results_dir`. `base_module.BaseAnalysisModule` define o contrato
(nem todos os módulos herdam dela ainda — ver "Dívidas conhecidas").

| Módulo | Técnica | Dependências-chave |
|--------|---------|--------------------|
| `file_analysis.py` | Hash SHA-512, metadados ffprobe, GOP, rastros de software de edição | FFmpeg |
| `structure_analysis.py` | Ordem dos átomos ISO BMFF (`moov`/`mdat`) → captura vs edição | — (parsing binário próprio) |
| `continuity.py` | Detecção de cortes (SCDET) e anomalias PTS/DTS | FFmpeg |
| `compression_analysis.py` | Dupla compressão: Lei de Benford + periodicidade de GOP (FFT) | numpy, scipy |
| `quantization_analysis.py` | Scaling lists H.264, estatísticas de QP, BPP → assinatura de encoder | FFmpeg (`trace_headers`) |
| `prnu_analysis.py` | Fingerprint de sensor (PRNU) com wavelets; comparação por PCE | OpenCV, PyWavelets |
| `image_forensics.py` | ELA, ruído, DCT, copy-move (SIFT), resampling, JPEG ghosts | OpenCV, scikit-image |
| `deepfake_analysis.py` | Artefatos GAN (FFT), textura (LBP), jitter temporal, detecção de faces | OpenCV |
| `audio_forensics.py` | Espectro, fase, piso de ruído, silêncio anômalo | librosa |
| `audio_deepfake.py` | Heurísticas de voz sintética (mel, formantes, pitch, micro-pausas) | librosa |
| `reporting.py` | Consolida JSONs → LaTeX → PDF (`pdflatex`) | LaTeX no PATH |

## Camada `adapters/`

`FFmpegAdapter` encapsula todas as chamadas a `ffmpeg`/`ffprobe` com logging
auditado dos comandos executados. Lança `RuntimeError` no construtor se os
binários não estiverem no PATH.

## Estrutura de saída por caso

```
cases/case_<NOME>/
├── execution.log            # Auditoria JSONL com hash chain
├── evidence_manifest.json   # Manifesto de evidências
├── results/                 # Um JSON por módulo + batch_manifest.json + *.npy (PRNU)
└── report/                  # report.pdf / report.tex e relatórios individuais
```

## Testes

A suíte automatizada vive em `tests/` (pytest) e cobre a lógica pura sem
dependências externas: hashing, logger/hash chain, configuração, CaseManager,
parsing ISO BMFF e estatísticas Benford/Fourier. Módulos que dependem de
FFmpeg/arquivos reais são exercitados pelos scripts manuais em `scripts/debug/`.

```bash
python -m pytest            # suíte completa
python -m pytest --cov      # com cobertura
```

## Build e distribuição

- `build_executable.bat` — gera `VerificacaoEdicao.exe` (GUI) e `VerificacaoEdicao_CLI.exe` via PyInstaller e, se o Inno Setup 6 estiver instalado, o instalador em `dist-setup/`.
- `setup_script.iss` — script do Inno Setup (instalador Windows, pt-BR).
- `tools/update_version.py` — incrementa a versão em `app/version.py` a cada build.

## Dívidas técnicas conhecidas

- `modules/reporting.py` (~2.300 linhas) concentra toda a geração LaTeX e
  conhece as chaves dos JSONs de cada módulo; não há versionamento de schema
  dos resultados. Mudanças no formato de saída de um módulo exigem revisão
  manual do reporting.
- Nem todos os módulos herdam de `BaseAnalysisModule`; o tratamento de erros
  varia entre retornar `{"error": ...}` e lançar exceção.
- Não há fallback quando `pdflatex` falha (o `.tex` fica órfão).
- O monitoramento de cluster usa arquivos compartilhados (heartbeat JSON) sem
  detecção de falha de nó.
