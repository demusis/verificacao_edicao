"""
Execução padronizada de processos externos (FFmpeg, FFprobe, pdflatex).

Centraliza três proteções que todas as chamadas externas precisam:

1. **Timeout** — um binário travado (arquivo corrompido, rede instável)
   não pode congelar o pipeline indefinidamente.
2. **Encoding UTF-8 tolerante** — no Windows, ``text=True`` usa a codepage
   legada (cp1252) por padrão; metadados com acentos causariam
   ``UnicodeDecodeError``.
3. **Sem janela de console** — quando a GUI (PyInstaller windowed) invoca
   binários externos no Windows, evita o "piscar" de janelas de console.
"""
import subprocess
import sys

#: Evita janelas de console ao chamar binários a partir da GUI no Windows.
CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

#: Timeout padrão (s) — generoso para não interromper análises legítimas.
DEFAULT_TIMEOUT = 600

#: Timeout (s) para operações que percorrem o arquivo inteiro (vídeos longos).
LONG_TIMEOUT = 3600


def run_command(
    cmd: list[str],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    check: bool = False,
    cwd: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Executa um comando externo com proteções padrão.

    Args:
        cmd: Comando e argumentos.
        timeout: Tempo máximo em segundos (lança ``TimeoutExpired``).
        check: Se True, lança ``CalledProcessError`` em exit code != 0.
        cwd: Diretório de trabalho opcional.

    Returns:
        CompletedProcess com stdout/stderr decodificados em UTF-8.

    Raises:
        subprocess.TimeoutExpired: Se o comando exceder o timeout.
        subprocess.CalledProcessError: Se check=True e exit code != 0.
    """
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=check,
        cwd=cwd,
        creationflags=CREATION_FLAGS,
    )
