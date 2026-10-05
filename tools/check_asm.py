#!/usr/bin/env python3
"""
One-shot validation: GNU-assemble every test program, run it on the
golden Python ISS (tools/rvsim.py), and sanity-check the result:
  * the program must terminate on ebreak (model halt),
  * it must not store over its own .text,
  * it must not trap (mcause stays 0 unless the test is a trap test).
Exits non-zero if any program fails.

Run:  python3 tools/check_asm.py
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gnuasm, rvsim

TRAP_TESTS = {"trap"}
ok = True
for name in sorted(f for f in os.listdir(os.path.join(ROOT, "tests", "asm"))
                   if f.endswith(".S")):
    path = os.path.join(ROOT, "tests", "asm", name)
    base = os.path.basename(path)[:-2]
    try:
        img = gnuasm.assemble_file(path, 0)   # RTL loads at address 0
    except Exception as e:
        print(f"FAIL {base}: assemble error: {e}")
        ok = False
        continue
    tt = gnuasm.text_top(path, 0)
    iss = rvsim.ISS(bytearray(img), max_steps=100000, base=0, text_top=tt)
    iss.run()
    if iss.clobbered:
        print(f"FAIL {base}: program stored into its own .text")
        ok = False
        continue
    if not iss.done:
        print(f"FAIL {base}: ISS did not halt after {len(iss.trace)} steps")
        for pc, inst, r, w in iss.trace[-5:]:
            print(f"  {pc:08x} ({inst:08x}) x{r} {w:08x}")
        ok = False
        continue
    if base not in TRAP_TESTS and iss.mcause != 0:
        print(f"FAIL {base}: unexpected trap (mcause={iss.mcause})")
        ok = False
        continue
    print(f"PASS {base}: {len(iss.trace)} steps")

sys.exit(0 if ok else 1)
