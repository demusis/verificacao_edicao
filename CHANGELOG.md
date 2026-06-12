# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

## [Não lançado]

### Adicionado
- **Hash chain no log de auditoria** (`core/logger.py`): cada evento de
  `execution.log` agora carrega `prev_hash` e `event_hash` (SHA-256),
  permitindo detectar alteração, remoção, inserção ou reordenação de eventos.
  Logs antigos permanecem legíveis (reportados como `legacy_events`).
- `tools/verify_audit_log.py` — verificador de integridade da trilha de
  auditoria para uso pericial (exit code 0 = íntegro).
- Suíte de testes automatizados em `tests/` (51 testes): hashing, logger e
  cenários de adulteração da cadeia, configuração tipada, CaseManager,
  parsing ISO BMFF (incluindo átomo malformado/anti-loop) e estatísticas
  Benford/Fourier, com regressão do retorno de
  `CompressionAnalysisModule.run()`.
- Documentação: `docs/ARCHITECTURE.md`, `CONTRIBUTING.md`, `scripts/README.md`.

### Corrigido (pente-fino)
- **Subprocessos centralizados** em `core/subprocess_utils.run_command`:
  todas as chamadas a ffmpeg/ffprobe/pdflatex agora têm timeout, encoding
  UTF-8 com `errors="replace"` (corrige texto corrompido em consoles cp1252)
  e `CREATE_NO_WINDOW` (elimina flash de console no app empacotado).
  Aplicado em: `adapters/ffmpeg_adapter.py`, `core/hashing.py`,
  `modules/continuity.py`, `modules/quantization_analysis.py`,
  `modules/audio_forensics.py`, `modules/reporting.py` (pdflatex) e
  `app/gui.py` (detecção de stream de vídeo e thumbnails).
- **Compatibilidade ffprobe 5+**: `pkt_pts_time` foi renomeado para
  `pts_time`; o adapter agora solicita e aceita ambos os campos.
- `modules/compression_analysis.py`: `run()` não retornava o resultado em
  caso de sucesso (sempre `None`) — agora retorna `result_data`.
- `modules/prnu_analysis.py`: `.npy` só é salvo se a extração funcionou;
  novo campo `frames_used` no JSON; `cap.release()` em `finally`;
  guard de máscara vazia no cálculo de energia do PCE.
- `modules/audio_forensics.py`: conversões numéricas tolerantes a `N/A`
  nos metadados; guards contra divisão por zero/array vazio na análise de
  noise floor e silêncio digital.
- `modules/deepfake_analysis.py`: `cap.release()` em `finally` no fluxo de
  vídeo (handle não vazava mais em caso de exceção por frame).
- `modules/image_forensics.py`: guard de entropia para bloco vazio; média
  de entropias com lista vazia; limpeza garantida (try/finally) do JPEG
  temporário do ELA; remoção de variáveis mortas.
- `modules/structure_analysis.py`: parser de átomos agora aborta em átomos
  com tamanho menor que o cabeçalho (evita loop infinito em arquivo
  malformado).
- `modules/continuity.py`: alerta `SCENE_DETECT_WARNING` quando o showinfo
  produz linhas que a regex não reconhece (mudança de formato do ffmpeg
  não é mais mascarada como "zero cortes").
- `app/gui.py`: `AnalysisWorker` agora usa `AnalysisConfig()` como default
  (o fallback `{}` quebrava em `config.prnu_frame_limit` e fazia todos os
  `getattr` retornarem default silenciosamente); checagens de
  `node_info_path` nulo; bare `except:` substituídos por
  `except Exception`; `print()` substituído por sinais de progresso;
  bloco morto duplicado removido em `_process_single_file`.
- `app/cluster_dashboard.py` e `app/reconstruct_manifest.py`: bare excepts
  e `assert` redundante removidos.
- Lint `ruff` zerado em `app/`, `core/`, `modules/`, `adapters/`, `tools/`
  e `tests/` (era 57 avisos residuais após a primeira passada).

### Alterado
- `core/logger.py` agora é thread-safe (lock de escrita) — a GUI usa o logger
  a partir de múltiplas threads (worker de análise + heartbeat).
- Scripts ad-hoc de depuração movidos da raiz para `scripts/debug/`;
  wheels offline movidos para `vendor/wheels/`.
- `.gitignore` ampliado (executáveis, wheels, artefatos de build e saídas de
  teste); binários `ac.exe` e `AnaliseConteudo_CLI.exe` removidos do controle
  de versão (permanecem no disco).
- README: estrutura de saída corrigida (`execution.log` na raiz do caso, e não
  `audit/audit.jsonl`), seções de verificação de integridade e desenvolvimento.
