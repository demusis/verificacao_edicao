# Guia de Contribuição

Obrigado por contribuir com o **VerificacaoEdicao**. Este guia descreve o fluxo
de desenvolvimento. Para entender o sistema, leia [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Ambiente de desenvolvimento

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
pip install pytest pytest-cov ruff mypy
```

Requisitos externos: **FFmpeg** no PATH (obrigatório) e **LaTeX/pdflatex**
(apenas para geração de relatórios).

## Fluxo de trabalho

1. Crie um branch a partir de `main`.
2. Faça alterações pequenas e focadas; mantenha o estilo do código existente.
3. Rode testes e linter antes de submeter (abaixo).
4. Escreva mensagens de commit descritivas no imperativo (`fix: ...`, `feat: ...`).

## Testes

Toda mudança em `core/` ou em lógica pura de `modules/` deve vir acompanhada de
testes em `tests/`:

```bash
python -m pytest               # suíte completa
python -m pytest --cov         # com relatório de cobertura
python -m pytest tests/test_logger.py -k chain   # subset
```

Diretrizes:

- Testes não devem depender de FFmpeg, rede ou arquivos de mídia reais — use
  `tmp_path` e dados sintéticos (veja `tests/test_structure_analysis.py`).
- Scripts exploratórios/manuais pertencem a `scripts/debug/`, não a `tests/`.

## Qualidade de código

```bash
ruff check .        # lint (config no pyproject.toml, line-length 100)
ruff format .       # formatação
mypy core modules   # checagem de tipos
```

- Docstrings em português, estilo Google (Args/Returns/Raises), como em `core/logger.py`.
- Configuração nova deve entrar em `core/config_schema.py` (dataclass tipada),
  nunca como dicionário avulso.
- Novos módulos de análise devem herdar de `modules/base_module.BaseAnalysisModule`
  e gravar resultados via `_save_results()`.

## Cuidados específicos do domínio forense

- **Nunca** altere o formato do log de auditoria sem manter compatibilidade
  retroativa — logs antigos precisam continuar verificáveis
  (`python tools/verify_audit_log.py <execution.log>`).
- O hash chain do logger (`core/logger.py`) é garantia de integridade da
  trilha de auditoria: mudanças ali exigem atualização dos testes de
  adulteração em `tests/test_logger.py`.
- Resultados de módulos são insumo de laudos periciais: mudanças nas chaves
  dos JSONs de saída exigem revisão de `modules/reporting.py`.

## Build (Windows)

```bash
build_executable.bat        # gera GUI + CLI em dist/ e instalador em dist-setup/
```

O script incrementa a versão automaticamente via `tools/update_version.py`.
Não versione binários (`.exe`, `.whl`) — o `.gitignore` já os exclui.
