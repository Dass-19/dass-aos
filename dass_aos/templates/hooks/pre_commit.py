#!/usr/bin/env python3
"""DASS-AOS git pre-commit hook: runs `aos verify` if DASS-AOS is installed."""
import importlib.util
import subprocess
import sys


def main() -> int:
    if importlib.util.find_spec("dass_aos") is None:
        print("[DASS-AOS] dass-aos no esta instalado en este Python; se omite verify (pip install dass-aos).")
        return 0
    print("[DASS-AOS] Ejecutando verificacion pre-commit...")
    res = subprocess.run([sys.executable, "-m", "dass_aos", "verify"], check=False)
    if res.returncode != 0:
        print("[DASS-AOS] La verificacion fallo. Corrige los problemas antes de commitear.", file=sys.stderr)
    return res.returncode


if __name__ == "__main__":
    sys.exit(main())
