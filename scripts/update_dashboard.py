#!/usr/bin/env python3
"""Explicit operator CLI. Never invoked by the web panel or scheduled automatically."""
import argparse
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard.update_manager import UpdateError, UpdateManager


def main():
    parser = argparse.ArgumentParser(description="ST7789: preparação isolada, troca verificada e retorno de código/ambiente.")
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight")
    commands.add_parser("status")
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--revision", required=True, help="SHA completo de uma revisão Git local confiável")
    for command in ("activate", "rollback"):
        action = commands.add_parser(command)
        action.add_argument("release")
        action.add_argument("--confirm", required=True, action="store_true", help="confirma pausa/troca dos serviços ativos")
    args = parser.parse_args()
    os.umask(0o077)
    if sys.platform != "linux" or os.geteuid() == 0:
        parser.exit(1, "Execute no Raspberry como usuário normal, não como root.\n")
    try:
        manager = UpdateManager(args.repository)
        if args.command == "preflight":
            previous, _ = manager.preflight()
            print(f"PASS instalação padrão saudável v{previous['version']}; nenhuma troca realizada.")
        elif args.command == "status":
            if manager.root.exists():
                with manager.locked():
                    for release in sorted(manager.root.glob("release-*")):
                        manifest = manager.read(release.name)
                        print(f"{release.name} {manifest['phase']} {manifest.get('candidate', {}).get('version', '-')}")
            else:
                print("Nenhum release preparado.")
        elif args.command == "prepare":
            print("Preparação: backup privado, ambiente separado, dependências e testes; pode levar alguns minutos.", flush=True)
            release = manager.prepare(args.revision)
            print(f"PASS release preparado: {release}\nServiços ativos e ambiente anterior preservados. Ativação é uma ação separada.")
        else:
            print(getattr(manager, args.command)(args.release))
        return 0
    except (UpdateError, OSError, ValueError, KeyError, KeyboardInterrupt):
        # No raw exception/traceback: it could contain config, URLs or credentials.
        error = sys.exception()
        message = str(error) if isinstance(error, UpdateError) else "Operação interrompida ou falhou. Confira status; preserve os diretórios de recuperação."
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
