#!/usr/bin/env python3
"""Run the whole verification stack end to end.

Stages:
  1. golden-model self-check: every tests/asm/*.S must run to ebreak on
     the Python ISS without clobbering .text (tools/check_asm.py).
  2. Spike cross-check: the ISS retirement stream must match Spike
     (tools/check_spike.py; trap.S matches only up to the trap).
  3. regenerate cpu/src/test/gen_cpu_tests.veryl from the same programs.
  4. `veryl test` --sim verilator: per-unit tests + 7 SoC integration
     tests, all comparing the RTL against the golden retire trace and
     final RAM image.

Run from the repo root:  python3 tools/run_all.py
"""
import subprocess
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(cmd, cwd=ROOT):
    print(f"\n$ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=cwd)
    if r.returncode != 0:
        sys.exit(f"FAILED: {' '.join(cmd)} (rc={r.returncode})")


def main():
    run([sys.executable, "tools/check_asm.py"])
    run([sys.executable, "tools/check_spike.py"])
    run([sys.executable, "tools/gen_tests.py"])
    run(["veryl", "test", "--sim", "verilator"], cwd=os.path.join(ROOT, "cpu"))
    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
