#!/usr/bin/env python3
"""
Validate the golden Python ISS (tools/rvsim.py) against Spike, the
official RISC-V ISA simulator.

For every tests/asm/*.S:
  1. link with GNU as/ld at 0x80000000 (Spike's RAM base), ebreak -> nop
     so Spike keeps running past the program's halt point,
  2. run Spike with --log-commits, parse the retired (pc, inst, rd, wval),
  3. run the Python ISS on the same image,
  4. diff the two retirement streams instruction by instruction.

Run:  python3 tools/check_spike.py
"""
import os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gnuasm, rvsim

SPIKE = os.path.expanduser("~/.local/bin/spike")
BASE = 0x80000000

COMMIT = re.compile(
    r"core\s+0: 3 0x([0-9a-f]+) \(0x([0-9a-f]{8})\)(?:\s+x(\d+)\s+0x([0-9a-f]+))?")

def spike_commits(elf, n):
    """Return (commits, stopped_at_exception).

    Spike in this configuration stops retiring once a trap is taken
    (it does not vector to the program's handler), so execution may
    end early at an exception; callers get the flag to compare only
    the common prefix in that case."""
    out = subprocess.run([SPIKE, "--isa=rv32i_zicsr", "-l", "--log-commits",
                          f"--instructions={3 * n + 64}", elf],
                         capture_output=True, text=True).stderr
    commits = []
    exc = False
    for line in out.splitlines():
        if "exception trap_" in line:
            exc = True
            break
        m = COMMIT.search(line)
        if not m:
            continue
        pc, inst = int(m.group(1), 16), int(m.group(2), 16)
        if pc < BASE:
            continue          # Spike boot ROM
        rd = int(m.group(3)) if m.group(3) is not None else None
        wv = int(m.group(4), 16) if m.group(4) is not None else None
        commits.append((pc, inst, rd, wv))
    return commits, exc

def main():
    ok = True
    for name in sorted(os.listdir(os.path.join(ROOT, "tests", "asm"))):
        if not name.endswith(".S"):
            continue
        path = os.path.join(ROOT, "tests", "asm", name)
        # run past the halt point: turn ebreak into a self-loop so both
        # simulators keep retiring identical instructions
        src = open(path).read().replace("ebreak", "j .")
        with tempfile.NamedTemporaryFile("w", suffix=".S", delete=False) as f:
            f.write(src)
            tmp = f.name
        elf = tempfile.mktemp(suffix=".elf")
        try:
            gnuasm.link_elf(tmp, elf, BASE)
            img = gnuasm.assemble_file(tmp, BASE)
            tt = gnuasm.text_top(tmp, BASE)
            iss = rvsim.ISS(bytearray(img), max_steps=1000, base=BASE, text_top=tt)
            iss.run()
            commits, exc = spike_commits(elf, len(iss.trace) + 8)
        finally:
            os.unlink(tmp)
            if os.path.exists(elf):
                os.unlink(elf)

        # The ISS trace records (pc, inst, rd, wval); Spike records the
        # register write only when one actually happened.
        if exc:
            # Spike stopped at the first trap: only the retired prefix
            # up to the trapping instruction is comparable.
            n = len(commits)
            if n > len(iss.trace):
                print(f"FAIL {name}: spike retired {n} before trap but ISS {len(iss.trace)}")
                ok = False
                continue
        else:
            n = len(iss.trace)
        if n == 0:
            print(f"FAIL {name}: ISS retired nothing")
            ok = False
            continue
        bad = None
        for i in range(n):
            if i >= len(commits):
                bad = (i, "spike retired fewer instructions than ISS")
                break
            ipc, iinst, ird, iwd = iss.trace[i]
            spc, sint, srd, swd = commits[i]
            if ipc != spc or iinst != sint:
                bad = (i, f"pc/inst {ipc:08x}/{iinst:08x} != {spc:08x}/{sint:08x}")
                break
            # Spike reports the register write only when a real one
            # happened (rd != 0). Compare it; skip everything else.
            if srd not in (None, 0):
                if ird != srd or iwd != swd:
                    bad = (i, f"regwrite x{ird}=0x{iwd:08x} != x{srd}=0x{swd:08x}")
                    break
            if srd == 0 and ird != 0:
                bad = (i, f"rd mismatch: ISS rd={ird} spike rd=0")
                break
        if bad:
            ok = False
            print(f"FAIL {name}: first mismatch at retire #{bad[0]}: {bad[1]}")
        else:
            tag = " (prefix up to trap)" if exc else ""
            print(f"PASS {name}: ISS matches Spike over {n} retirements{tag}")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
