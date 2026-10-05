#!/usr/bin/env python3
"""
Generate the Veryl integration tests for the RV32I CPU.

For every program in tests/asm/*.S:
  1. assemble it with tools/vasm.py,
  2. run it on the golden ISS (tools/rvsim.py) to get the expected
     retire trace (pc, rd, wdata) and the final RAM image,
  3. emit a #[test] module in cpu/src/test/gen_<name>.veryl that
     loads the program through the Soc loader ports, runs the SoC and
     compares the retire trace against the golden model, instruction
     by instruction, plus the final RAM contents.

Run:  python3 tools/gen_tests.py
"""
import os, sys, importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gnuasm, rvsim

ASM_DIR = os.path.join(ROOT, "tests", "asm")
OUT_DIR = os.path.join(ROOT, "cpu", "src", "test")
WORDS = 1024
MAX_CYCLES = 4000


def golden(prog_path):
    img = gnuasm.assemble_file(prog_path, 0)
    tt = gnuasm.text_top(prog_path, 0)
    iss = rvsim.ISS(bytearray(img), max_steps=20000, trace=True, base=0,
                    text_top=tt)
    # run until ebreak sets done
    iss.run()
    trace = [(pc, rd, wd) for pc, inst, rd, wd in iss.trace]
    # pad image to WORDS
    mem = bytes(iss.mem[: WORDS * 4]).ljust(WORDS * 4, b"\0")
    return img, trace, mem


def emit(name, img, trace, mem, f):
    f.write(f"/// Auto-generated integration test for tests/asm/{name}.S\n")
    f.write(f"/// Golden trace: {len(trace)} retired instructions.\n")
    f.write("#[allow(unused_variable)]\n")
    f.write(f"#[test(test_{name})]\n")
    f.write(f"module test_{name} {{\n")
    f.write("    inst clk: $tb::clock_gen;\n")
    f.write("    #[allow(initial_assign)]\n    var rst: reset;\n\n")
    f.write("    var halt: logic;\n")
    f.write("    var retire: logic;\n")
    f.write("    var rpc: logic<32>;\n")
    f.write("    var rrd: logic<5>;\n")
    f.write("    var rwdata: logic<32>;\n")
    f.write("    #[allow(initial_assign)]\n    var load_en: logic;\n")
    f.write("    #[allow(initial_assign)]\n    var load_addr: logic<30>;\n")
    f.write("    #[allow(initial_assign)]\n    var load_wdata: logic<32>;\n")
    f.write("    #[allow(initial_assign)]\n    var n: logic<32>;\n\n")
    f.write("    inst dut: rv32i_soc #(\n")
    f.write(f"        WORDS: {WORDS},\n")
    f.write("    ) (\n")
    f.write("        i_clk: clk,\n")
    f.write("        i_rst: rst,\n")
    f.write("        o_inst_retire: retire,\n")
    f.write("        o_retire_pc  : rpc,\n")
    f.write("        o_retire_rd  : rrd,\n")
    f.write("        o_retire_wdata: rwdata,\n")
    f.write("        o_halt       : halt,\n")
    f.write("        i_load_en    : load_en,\n")
    f.write("        i_load_addr  : load_addr,\n")
    f.write("        i_load_wdata : load_wdata,\n")
    f.write("    );\n\n")
    f.write("    // golden retire trace\n")
    f.write("    #[allow(initial_assign)]\n")
    f.write(f"    var gpc: logic<32> [{max(len(trace),1)}];\n")
    f.write("    #[allow(initial_assign)]\n")
    f.write(f"    var grd: logic<5> [{max(len(trace),1)}];\n")
    f.write("    #[allow(initial_assign)]\n")
    f.write(f"    var gwd: logic<32> [{max(len(trace),1)}];\n")
    f.write("    initial {\n")
    for i, (pc, rd, wd) in enumerate(trace):
        f.write(f"        gpc[{i}] = 32'h{pc:08x}; grd[{i}] = 5'd{rd}; gwd[{i}] = 32'h{wd:08x};\n")
    f.write("    }\n\n")
    # golden RAM words that differ from zero
    nonzero = [(i, int.from_bytes(mem[i*4:i*4+4], "little"))
               for i in range(WORDS) if mem[i*4:i*4+4] != b"\0\0\0\0"]
    if nonzero:
        f.write("#[allow(initial_assign)]\n")
        f.write(f"    var gmem: logic<32> [{len(nonzero)}];\n")
        f.write("#[allow(initial_assign)]\n")
        f.write(f"    var gaddr: logic<30> [{len(nonzero)}];\n")
        f.write("    initial {\n")
        for i, (w, v) in enumerate(nonzero):
            f.write(f"        gmem[{i}] = 32'h{v:08x}; gaddr[{i}] = 30'd{w};\n")
        f.write("    }\n\n")
    f.write("    initial {\n")
    f.write("        // hold the core in reset while loading the program\n")
    f.write("        // (RAM itself has no reset)\n")
    f.write("        rst = 1;\n")
    f.write("        load_en = 1;\n")
    for wi in range(len(img) // 4):
        word = int.from_bytes(img[wi * 4:wi * 4 + 4], "little")
        f.write(f"        load_addr = 30'd{wi}; load_wdata = 32'h{word:08x}; clk.next();\n")
    f.write("        load_en = 0;\n")
    f.write("        rst = 0;\n")         # release reset: start execution
    f.write("        // run and check trace\n")
    f.write("        n = 0;\n")
    f.write("        for cyc in 0..MAXCYC {\n")
    f.write("            clk.next();\n")
    f.write("            if retire && n <= TRN - 1 {\n")
    f.write("                $assert(rpc == gpc[n], \"pc mismatch at %d: %h != %h\", n, rpc, gpc[n]);\n")
    f.write("                $assert(rrd == grd[n], \"rd mismatch at %d: %d != %d\", n, rrd, grd[n]);\n")
    f.write("                if grd[n] != 0 {\n")
    f.write("                    $assert(rwdata == gwd[n], \"wdata mismatch at %d pc=%h: %h != %h\", n, rpc, rwdata, gwd[n]);\n")
    f.write("                }\n")
    f.write("                n += 1;\n")
    f.write("            }\n")
    f.write("            if halt {\n")
    f.write("                break;\n")
    f.write("            }\n")
    f.write("        }\n")
    f.write("        $assert(n == TRN, \"retired %d instructions, expected %d\", n, TRN);\n")
    if nonzero:
        f.write(f"        for i in 0..{len(nonzero)} {{\n")
        f.write("            $assert(dut.mem[gaddr[i]] == gmem[i], \"mem[%d] mismatch: %h != %h\", gaddr[i], dut.mem[gaddr[i]], gmem[i]);\n")
        f.write("        }\n")
    f.write("        $finish();\n")
    f.write("    }\n")
    f.write("}\n\n")
    # fix placeholders
    # (done by caller-level replace)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    progs = sorted(f for f in os.listdir(ASM_DIR) if f.endswith(".S"))
    if not progs:
        print("no test programs found")
        return
    out = os.path.join(OUT_DIR, "gen_cpu_tests.veryl")
    with open(out, "w") as f:
        f.write("// Generated by tools/gen_tests.py -- do not edit by hand.\n\n")
        for name in progs:
            prog_path = os.path.join(ASM_DIR, name)
            base = name[:-2]
            img, trace, mem = golden(prog_path)
            emit(base, img, trace, mem, f)
    # substitute constants
    s = open(out).read()
    s = s.replace("MAXCYC", str(MAX_CYCLES))
    # per-test TRN
    import re
    parts = re.split(r"(?=#\[test\(test_)", s)
    fixed = []
    for part in parts:
        m = re.search(r"var gpc: logic<32> \[(\d+)\];", part)
        if m:
            part = part.replace("TRN", m.group(1))
        fixed.append(part)
    open(out, "w").write("".join(fixed))
    print(f"wrote {out} ({len(progs)} tests)")


if __name__ == "__main__":
    main()
