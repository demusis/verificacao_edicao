"""
Verificador de integridade do log de auditoria (hash chain).

Confere a cadeia criptográfica de um ``execution.log`` gerado pelo sistema,
detectando eventos alterados, removidos, inseridos ou reordenados.

Uso (a partir da raiz do projeto):
    python tools/verify_audit_log.py cases/case_EXEMPLO/execution.log

Código de saída: 0 se a cadeia está íntegra, 1 caso contrário.
"""
import argparse
import sys
from pathlib import Path

# Permite executar o script diretamente, sem instalar o pacote.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Console do Windows pode usar codepage legada (cp1252/cp850); força UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from core.logger import Logger


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verifica a integridade (hash chain) de um log de auditoria."
    )
    parser.add_argument("log_file", type=Path, help="Caminho do execution.log")
    args = parser.parse_args()

    if not args.log_file.is_file():
        print(f"ERRO: arquivo não encontrado: {args.log_file}")
        return 1

    report = Logger(args.log_file).verify_chain()

    print(f"Arquivo:             {args.log_file}")
    print(f"Total de eventos:    {report['total_events']}")
    print(f"Eventos verificados: {report['verified_events']}")
    if report["legacy_events"]:
        print(
            f"Eventos legados:     {report['legacy_events']} "
            "(gravados antes do hash chain; sem garantia criptográfica)"
        )

    if report["valid"]:
        print("RESULTADO: ÍNTEGRO — cadeia de hashes válida.")
        return 0

    print("RESULTADO: VIOLAÇÃO DETECTADA — a cadeia de hashes está quebrada:")
    for error in report["errors"]:
        print(f"  - Evento #{error['index']}: {error['reason']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
