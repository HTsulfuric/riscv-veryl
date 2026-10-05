#!/usr/bin/env python3
"""
Golden RV32I reference model (ISS) used to cross-check the assembler and
to generate expected retire-traces for the Veryl CPU tests.
Runs the same flat memory image the SoC uses: one RAM, byte-addressed,
word-aligned base at 0. Traps: illegal/ebreak jump to 0x4, MRET returns.
"""
import struct, sys

MASK = 0xFFFFFFFF

def s32(v):
    v &= MASK
    return v - (1 << 32) if v & 0x80000000 else v

def sext(v, bits):
    """sign-extend a `bits`-wide two's-complement field"""
    m = 1 << (bits - 1)
    v &= (1 << bits) - 1
    return (v ^ m) - m

class ISS:
    def __init__(self, mem, max_steps=100000, trace=True, base=0, text_top=None):
        self.mem = bytearray(mem)          # flat RAM, little endian
        self.base = base                   # address where mem[0] lives
        self.x = [0] * 32
        self.pc = base
        self.mcause = 0
        self.mepc = 0
        self.mscratch = 0
        self.mtvec = base + 0x4   # reset vector, relative to RAM base
        self.max_steps = max_steps
        self.trace = [] if trace else None
        self.stores = [] if trace else None
        self.done = False
        self.prog_top = len(self.mem)
        if text_top is not None:            # absolute VMA end of .text
            self.prog_top = text_top - base
        self.clobbered = False

    def rmem(self, addr, size):
        idx = (addr & MASK) - self.base
        if idx + size > len(self.mem):
            self.mem.extend(b"\0" * (idx + size - len(self.mem)))
        return struct.unpack("<" + {1: "B", 2: "H", 4: "I"}[size],
                             self.mem[idx:idx + size])[0]

    def wmem(self, addr, size, val):
        idx = (addr & MASK) - self.base
        if idx + size > len(self.mem):
            self.mem.extend(b"\0" * (idx + size - len(self.mem)))
        self.mem[idx:idx + size] = struct.pack(
            "<" + {1: "B", 2: "H", 4: "I"}[size], val & {(1): 0xFF, (2): 0xFFFF, (4): MASK}[size])
        if idx < self.prog_top:
            self.clobbered = True   # program wrote over its own instructions

    def rd_csr(self, a):
        return {0x305: self.mtvec, 0x340: self.mscratch,
                0x341: self.mepc, 0x342: self.mcause}.get(a, 0)

    def wr_csr(self, a, v):
        if a == 0x305: self.mtvec = v & MASK & ~3
        elif a == 0x340: self.mscratch = v
        elif a == 0x341: self.mepc = v
        elif a == 0x342: self.mcause = v

    def trap(self, cause):
        self.mcause = cause
        self.mepc = self.pc
        self.pc = self.mtvec & MASK

    def step(self):
        """execute one instruction; returns (pc, rd, wdata) or None"""
        pc = self.pc
        if pc & 3 or pc < self.base or pc - self.base >= len(self.mem):
            self.trap(2)
            return None
        inst = self.rmem(pc, 4)
        op = inst & 0x7F
        rd = (inst >> 7) & 31
        f3 = (inst >> 12) & 7
        rs1 = (inst >> 15) & 31
        rs2 = (inst >> 20) & 31
        imm_i = sext(inst >> 20, 12)
        imm_s = sext(((inst >> 25) << 5) | ((inst >> 7) & 0x1F), 12)
        imm_b = sext((((inst >> 31) & 1) << 12) | (((inst >> 25) & 0x3F) << 5) |
                     (((inst >> 8) & 0xF) << 1) | (((inst >> 7) & 1) << 11), 13)
        imm_u = inst & 0xFFFFF000
        imm_j = sext((((inst >> 31) & 1) << 20) | (((inst >> 12) & 0xFF) << 12) |
                     (((inst >> 20) & 1) << 11) | (((inst >> 21) & 0x3FF) << 1), 21)
        nxt = pc + 4
        wval = None
        a = self.x[rs1] if rs1 else 0
        b = self.x[rs2] if rs2 else 0

        if op == 0x37:   # LUI
            wval = imm_u
        elif op == 0x17: # AUIPC
            wval = (pc + imm_u) & MASK
        elif op == 0x6F: # JAL
            wval = pc + 4
            nxt = (pc + imm_j) & MASK
        elif op == 0x67: # JALR
            wval = pc + 4
            nxt = ((a + imm_i) & MASK) & ~1
        elif op == 0x63: # BRANCH
            t = {0: a == b, 1: a != b, 4: s32(a) < s32(b), 5: s32(a) >= s32(b),
                 6: a < b, 7: a >= b}.get(f3)
            if t is None:
                return self.trap(2)
            if t:
                nxt = (pc + imm_b) & MASK
        elif op == 0x03: # LOAD
            addr = (a + imm_i) & MASK
            if f3 == 0: wval = s32(self.rmem(addr, 1)) & MASK
            elif f3 == 1: wval = s32(self.rmem(addr, 2)) & MASK
            elif f3 == 2:
                if addr & 3: return self.trap(2)
                wval = self.rmem(addr, 4)
            elif f3 == 4: wval = self.rmem(addr, 1)
            elif f3 == 5: wval = self.rmem(addr, 2)
            else: return self.trap(2)
        elif op == 0x23: # STORE
            addr = (a + imm_s) & MASK
            if f3 == 0: self.wmem(addr, 1, b)
            elif f3 == 1: self.wmem(addr, 2, b)
            elif f3 == 2:
                if addr & 3: return self.trap(2)
                self.wmem(addr, 4, b)
            else: return self.trap(2)
            if self.trace is not None:
                self.stores.append((pc, addr, {0: 1, 1: 2, 2: 4}[f3], b))
        elif op == 0x13: # OP-IMM
            sh = imm_i & 0x1F
            if f3 == 0: wval = (a + imm_i) & MASK
            elif f3 == 1: wval = (a << sh) & MASK if imm_i < 0x20 else None
            elif f3 == 2: wval = 1 if s32(a) < s32(imm_i) else 0
            elif f3 == 3: wval = 1 if a < (imm_i & MASK) else 0
            elif f3 == 4: wval = a ^ (imm_i & MASK)
            elif f3 == 6: wval = a | (imm_i & MASK)
            elif f3 == 7: wval = a & (imm_i & MASK)
            elif f3 == 5:
                if imm_i & 0x400: wval = (s32(a) >> sh) & MASK
                elif imm_i < 0x20: wval = a >> sh
                else: wval = None
            if wval is None: return self.trap(2)
        elif op == 0x33: # OP
            f7 = inst >> 25
            sh = b & 0x1F
            if f3 == 0:
                if f7 == 0: wval = (a + b) & MASK
                elif f7 == 0x20: wval = (a - b) & MASK
                else: return self.trap(2)
            elif f3 == 1: wval = (a << sh) & MASK if f7 == 0 else None
            elif f3 == 2: wval = 1 if s32(a) < s32(b) else 0
            elif f3 == 3: wval = 1 if a < b else 0
            elif f3 == 4: wval = a ^ b
            elif f3 == 5:
                if f7 == 0: wval = a >> sh
                elif f7 == 0x20: wval = (s32(a) >> sh) & MASK
                else: wval = None
            elif f3 == 6: wval = a | b
            elif f3 == 7: wval = a & b
            if wval is None: return self.trap(2)

        elif op == 0x0F:  # FENCE: nop
            pass
        elif op == 0x73:  # SYSTEM
            if f3 == 0:
                csr = inst >> 20
                if inst == 0x00100073:   # EBREAK
                    self.done = True
                    return None
                elif inst == 0x30200073: # MRET
                    wval = None
                    nxt = self.mepc & MASK
                elif inst == 0x73:       # ECALL
                    return self.trap(11)
                else:
                    return self.trap(2)
            elif f3 in (1, 2, 3):
                csr = inst >> 20
                old = self.rd_csr(csr)
                src = a
                if f3 == 1: new = src
                elif f3 == 2: new = old | src
                else: new = old & ~src & MASK
                # spec: RW always writes; RS/RC skip when rs1==x0
                if f3 == 1 or rs1 != 0:
                    self.wr_csr(csr, new)
                wval = old
            elif f3 in (5, 6, 7):
                csr = inst >> 20
                old = self.rd_csr(csr)
                src = rs1  # zimm
                if f3 == 5: new = src
                elif f3 == 6: new = old | src
                else: new = old & ~src & MASK
                # spec: RWI always writes; RSI/RCI skip when zimm==0
                if f3 == 5 or src != 0:
                    self.wr_csr(csr, new)
                wval = old
            else:
                return self.trap(2)
        else:
            return self.trap(2)

        if rd != 0 and wval is not None:
            self.x[rd] = wval & MASK
        self.x[0] = 0
        self.pc = nxt & ~1
        if self.trace is not None:
            # retire trace mirrors the hardware: the raw rd field is
            # reported; wdata is only meaningful when rd != 0
            self.trace.append((pc, inst, rd, (wval or 0) & MASK))
        return (pc, rd, wval)

    def run(self):
        n = 0
        while n < self.max_steps and not self.done:
            n += 1
            self.step()
        return self.trace


if __name__ == "__main__":
    data = open(sys.argv[1], "rb").read()
    iss = ISS(data)
    iss.run()
    for pc, inst, r, w in iss.trace:
        print(f"{pc:08x} x{r} {w:08x}")
