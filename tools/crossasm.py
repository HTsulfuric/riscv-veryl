#!/usr/bin/env python3
"""
Cross-validate tools/vasm.py against GNU as (riscv64-linux-gnu-as).
Assembles every tests/asm/*.S with both assemblers and diffs the
resulting instruction words.

Run:  python3 tools/crossasm.py
"""
import os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

AS = "riscv64-linux-gnu-as"
OBJDUMP = "riscv64-linux-gnu-objdump"

def gnu_words(path):
    with tempfile.TemporaryDirectory() as td:
        o = os.path.join(td, "x.o")
        subprocess.run([AS, "-march=rv32i_zicsr", "-mabi=ilp32",
                        "-o", o, path], check=True)
        out = subprocess.run([OBJDUMP, "-d", "--show-raw-insn", o],
                             capture_output=True, text=True, check=True).stdout
    words = {}
    import re
    for line in out.splitlines():
        m = re.match(r"\s+([0-9a-f]+):\s+([0-9a-f]{8})\s", line)
        if m:
            words[int(m.group(1), 16)] = int(m.group(2), 16)
    return words

def image(path):
    w = gnu_words(path)
    if not w:
        return b""
    top = max(w) + 4
    img = bytearray(top)
    for a, v in w.items():
        img[a:a + 4] = v.to_bytes(4, "little")
    return bytes(img)

ok = True
for name in sorted(os.listdir(os.path.join(ROOT, "tests", "asm"))):
    if not name.endswith(".S"):
        continue
    path = os.path.join(ROOT, "tests", "asm", name)
    src = open(path).read()
    mine = vasm.assemble(src)
    gnu = gnu_words(path)
    n = max(len(gnu), len(mine) // 4)
    diffs = []
    for i in range(n):
        m = int.from_bytes(mine[i * 4:i * 4 + 4].ljust(4, b"\0"), "little")
        g = gnu.get(i * 4)
        if g is None:
            if m != 0:
                diffs.append((i * 4, m, None))
        elif m != g:
            diffs.append((i * 4, m, g))
    if diffs:
        ok = False
        print(f"FAIL {name}:")
        for a, m, g in diffs[:10]:
            gs = "missing" if g is None else f"{g:08x}"
            print(f"  {a:08x}: mine={m:08x} gnu={gs}")
    else:
        print(f"PASS {name}: {n} words identical to GNU as")

sys.exit(0 if ok else 1)
