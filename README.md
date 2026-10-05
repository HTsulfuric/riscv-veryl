# riscv-veryl — an RV32I CPU in Veryl

A 5-stage in-order RISC-V (RV32I) CPU written in [Veryl](https://veryl-lang.org)
(0.22), verified against two independent golden models and tested entirely
from Veryl with `veryl test`.

```
                     +--------------------- rv32i_core ---------------------+
  IF          ID              EX                  MEM               WB      |
  pc ---> [IF/ID] ---> [ID/EX] ---> [EX/MEM] ---> [MEM/WB] ---> regfile     |
   |         decode     alu/branch   load/store   write-back                |
   |         imm        csr/trap     sign-ext                              |
   +-- redirect (branch/jump/trap) --+   hazard unit: load-use stall       |
                     +------------------------------------------------------+
                     rv32i_soc = core + 4 KiB Harvard RAM (word-addressed)
```

## Layout

| path | what |
|---|---|
| `cpu/src/pkg.veryl` | opcodes, enums, pipeline payload structs, `Ctrl` |
| `cpu/src/pc.veryl` | fetch counter: +4 / stall / redirect |
| `cpu/src/pipe_reg.veryl` | generic pipeline register (flush/stall) |
| `cpu/src/decoder.veryl` | control word, immediates (I/S/B/U/J), branch code |
| `cpu/src/regfile.veryl` | 32x32 regfile, x0 hard-zero, write-through bypass |
| `cpu/src/alu.veryl` | ADD/SUB/SLL/SLT/SLTU/XOR/OR/AND/SHR(+SRA)/PASS |
| `cpu/src/execute.veryl` | branch eval, redirect targets, CSR RMW, traps |
| `cpu/src/memory.veryl` | load extension, memory request |
| `cpu/src/hazard.veryl` | load-use stall + redirect flush |
| `cpu/src/csr.veryl` | minimal M-mode CSRs (mtvec/mscratch/mcause/mepc) |
| `cpu/src/core.veryl` | pipeline wiring + operand forwarding |
| `cpu/src/soc.veryl` | core + RAM (sub-word byte lanes, test loader port) |
| `tests/asm/*.S` | 8 hand-written assembly programs |
| `tools/` | golden model + verification flow (Python) |
| `cpu/src/test/` | unit tests + generated integration tests |

## Microarchitecture

* **Stages**: IF, ID, EX, MEM, WB. Memory responds combinationally.
* **Hazards**
  * RAW distance 1: forward from EX/MEM; distance 2: from MEM/WB;
    distance 3: register-file write-through (the register file is read
    at EX). Load producers use the same network.
  * Load-use: 1-cycle stall — PC frozen, IF/ID held, bubble injected
    into ID/EX; the dependent instruction then reads the load value
    from MEM/WB.
  * Branches/jumps/traps resolve in EX; IF/ID and ID/EX are flushed.
* **Traps (M-mode only)**: illegal instruction (`mcause=2`) and EBREAK
  (`mcause=3`) vector to `mtvec` (reset 0x4, WARL-masked); trapped
  instructions do not retire. MRET returns to `mepc`. EBREAK additionally
  halts the core (`o_halt`).
* **Retire trace**: `o_inst_retire` pulses with `pc/rd/wdata` of every
  retiring instruction — the exact stream the golden ISS produces.

## Verification

```
tests/asm/*.S --GNU as/ld--> image --> Python ISS (tools/rvsim.py)
                                   |                    ^
                                   |                    | identical commits
                                   v                    v
                        tools/gen_tests.py          Spike (upstream ISS)
                                   |
                                   v
             cpu/src/test/gen_cpu_tests.veryl  (golden retire trace + RAM
                                   |            image baked into the test)
                                   v
                    veryl test --sim verilator  (RTL must match bit-exact)
```

* `tools/check_asm.py` — every program terminates on ebreak on the golden
  ISS without touching its own `.text`.
* `tools/check_spike.py` — the golden ISS must match upstream **Spike**
  commit-for-commit (trap.S compared up to the trap, since Spike stops
  there).  The golden model is not trusted either: the new edge.S
  cross-check immediately exposed and pinned down a latent sign-extension
  bug in the Python ISS's LB/LH (zero-extended instead of sign-extended),
  which the RTL itself had correct all along.
* `tools/gen_tests.py` — bakes the ISS retire trace + final RAM image of
  each program into a native Veryl test; the SoC under Verilator must
  reproduce both exactly.
* `cpu/src/test/test_*.veryl` — per-unit Veryl tests (`pc`, `pipe_reg`,
  `regfile`, `alu`, `decoder`, `execute`, `memory`, `hazard`, `csr`).

Run everything:

```sh
python3 tools/run_all.py          # golden checks + all 16 Veryl tests
```

or just the RTL tests:

```
cd cpu && veryl test --sim verilator
```

## Dependencies

* [veryl](https://github.com/veryl-lang/veryl) 0.22 + Verilator + a C
  compiler (`veryl test` native tests).
* GNU `riscv64-linux-gnu-as/ld/objdump` (32-bit objects, `-m elf32lriscv`)
  to assemble the programs.
* optional: [Spike](https://github.com/riscv-software-src/riscv-isa-sim)
  on `PATH` for `check_spike.py`.

## Status

RV32I complete: LUI/AUIPC/JAL/JALR, all branches, LB/LH/LW/LBU/LHU,
SB/SH/SW, ALU immediate/register forms, CSRRW/S/C(+I), ECALL traps as
illegal, EBREAK halt, MRET. No misaligned access support (they execute
lane-split as described by the byte lanes; the ISS models the same
behaviour), no interrupts, no hardware multiply (RV32M), single hart.
