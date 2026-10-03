"""Executa a suíte atual de testes (uma lista curada, sem os testes históricos de versões antigas).

Uso: python testes/run_suite.py     (no Linux/CI: xvfb-run -a python testes/run_suite.py)
"""
import subprocess, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
SUITE = [l.strip() for l in (HERE / 'SUITE_ATUAL.txt').read_text(encoding='utf-8').splitlines() if l.strip() and not l.startswith('#')]
failed = []
for name in SUITE:
    t = time.time()
    r = subprocess.run([sys.executable, str(HERE / name)], capture_output=True, text=True, timeout=900)
    ok = r.returncode == 0
    print(f"{'OK    ' if ok else 'FALHOU'} {name} ({time.time() - t:.1f}s)")
    if not ok:
        failed.append(name)
        print((r.stdout + r.stderr)[-1500:])
print(f"\n{len(SUITE) - len(failed)}/{len(SUITE)} testes passaram")
sys.exit(1 if failed else 0)
