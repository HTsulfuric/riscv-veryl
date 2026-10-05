#!/usr/bin/env python3
"""
Minimal RV32I assembler: a Python subset of GNU as for RV32I.
Supports the subset used by the CPU test programs:
  .word <expr>, .align <n>, .org <expr>, labels, comments (#, //)
  all RV32I instructions, register names x0..x31 and ABI aliases.
Emits a flat little-endian binary image.
"""
import re, sys

R = {}
for i in range(32):
    R[f"x{i}"] = i
abi = ["zero","ra","sp","gp","tp","t0","t1","t2","s0","fp","s1",
       "a0","a1","a2","a3","a4","a5","a6","a7",
       "s2","s3","s4","s5","s6","s7","s8","s9","s10","s11",
       "t3","t4","t5","t6"]
for i, n in enumerate(abi):
    R[n] = i

def reg(t):
    t = t.strip().lower()
    if t not in R:
        raise ValueError(f"bad register: {t}")
    return R[t]

def num(t, labels, pc):
    t = t.strip()
    hi_lo = re.fullmatch(r"%(hi|lo)\((\S+)\)", t)
    if hi_lo:
        v = num(hi_lo.group(2), labels, pc)
        return (v + 0x800) >> 12 if hi_lo.group(1) == "hi" else ((v & 0xFFF) - 0x1000 if v & 0x800 else v & 0xFFF)
    m = re.fullmatch(r"(-)?0x([0-9a-fA-F]+)", t)
    if m:
        v = int(m.group(2), 16)
        return -v if m.group(1) else v
    m = re.fullmatch(r"(0[bB][01_]+|-?(0[xX][0-9a-fA-F]+|\d+))", t)
    if m:
        v = int(m.group(1).replace("_", ""), 0)
        return v
    m = re.fullmatch(r"([a-zA-Z_][\w.]*|[a-zA-Z_][\w]*)([-+])(0x[0-9a-fA-F]+|\d+)", t)
    if m:
        base = num(m.group(1), labels, pc)
        off = num(m.group(3), labels, pc)
        return base + off if m.group(2) == "+" else base - off
    if t in labels:
        return labels[t]
    raise ValueError(f"unknown symbol: {t}")

def parse_mem(t):
    t = t.strip()
    m = re.fullmatch(r"\((.*)\)", t)
    if m:
        return 0, reg(m.group(1))
    m = re.fullmatch(r"(-?0x[0-9a-fA-F]+|-?\d+)\((.*)\)", t)
    if m:
        return int(m.group(1), 0), reg(m.group(2))
    m = re.fullmatch(r"([a-zA-Z_][\w.]*|[a-zA-Z_][\w]*)([-+](0x[0-9a-fA-F]+|\d+))?\((.*)\)", t)
    if m:
        base = num(m.group(1) + (m.group(2) or ""), globals_labels, cur_pc)
        return base, reg(m.group(4))
    raise ValueError(f"bad memory operand: {t}")

def field(v, lo, width):
    v >>= lo
    return (v & ((1 << width) - 1)) << lo

def enc_i(op, f3, rd, rs1, imm12):
    return op | (f3 << 12) | (rd << 7) | (rs1 << 15) | ((imm12 & 0xFFF) << 20)

def enc_s(op, f3, rs1, rs2, imm12):
    return op | (f3 << 12) | (rs1 << 15) | (rs2 << 20) | \
        (((imm12 >> 5) & 0x7F) << 25) | ((imm12 & 0x1F) << 7)

def enc_b(op, f3, rs1, rs2, imm13):
    return op | (f3 << 12) | (rs1 << 15) | (rs2 << 20) | \
        (((imm13 >> 12) & 1) << 31) | (((imm13 >> 5) & 0x3F) << 25) | \
        (((imm13 >> 1) & 0xF) << 8) | (((imm13 >> 11) & 1) << 7)

def enc_u(op, rd, imm32):
    return op | (rd << 7) | (imm32 & 0xFFFFF000)

def enc_j(op, rd, imm32):
    i = imm32
    return op | (rd << 7) | \
        (((i >> 20) & 1) << 31) | (((i >> 1) & 0x3FF) << 21) | \
        (((i >> 11) & 1) << 20) | (((i >> 12) & 0xFF) << 12)

def chk(v, lo, hi, what):
    if not (lo <= v <= hi):
        raise ValueError(f"{what} out of range: {v}")

globals_labels = {}
cur_pc = 0


class MultiLine(Exception):
    """raised when a pseudo expands to more than one instruction"""

def expand_li(lines):
    """Expand pseudo-instructions into real RV32I instructions."""
    out = []
    for raw in lines:
        m = re.fullmatch(r"liaddi\s+([-\w]+)\s*,\s*x0\s*,\s*(\S+)", raw)
        if m:
            out.append(raw.replace("liaddi", "addi", 1))
            continue
        m = re.fullmatch(r"addi\s+([-\w]+)\s*,\s*x0\s*,\s*(\S+)", raw)
        if m:
            try:
                v = num(m.group(2), globals_labels, cur_pc)
            except ValueError:
                pass  # symbolic: leave the addi with %lo() for the encoder
            else:
                if not (-2048 <= v <= 2047):
                    out.extend(expand_li([f"li {m.group(1)}, {v}"]))
                    continue
        m = re.fullmatch(r"li\s+([-\w]+)\s*,\s*(\S+)", raw)
        if m:
            rd, t = m.group(1), m.group(2)
            try:
                v = num(t, globals_labels, cur_pc)
            except ValueError:
                # symbolic value: emit a lui+addi pair sized for it
                out.append(f"lui {rd}, %hi({t})")
                out.append(f"addi {rd}, {rd}, %lo({t})")
                continue
            if -2048 <= v <= 2047:
                out.append(f"addi {rd}, x0, {v}")
            elif v & 0xFFF == 0:
                out.append(f"lui {rd}, {v >> 12}")
            else:
                hi = (v + 0x800) >> 12
                lo = v - (hi << 12)
                out.append(f"lui {rd}, {hi}")
                out.append(f"addi {rd}, {rd}, {lo}")
            continue
        m = re.fullmatch(r"la\s+([-\w]+)\s*,\s*(\S+)", raw)
        if m:
            rd, t = m.group(1), m.group(2)
            out.append(f"lui {rd}, %hi({t})")
            out.append(f"addi {rd}, {rd}, %lo({t})")
            continue
        out.append(raw)
    if len(out) != len(lines) or any(o.strip() != r.strip() for o, r in zip(out, lines)):
        return expand_li(out)
    return out


def assemble(text):
    global globals_labels, cur_pc
    labels = {}
    # pass 1: compute addresses
    sections = []
    pc = 0
    lines = []
    for raw in text.splitlines():
        raw = re.sub(r"//.*$", "", raw)
        raw = re.sub(r"#.*$", "", raw)
        raw = raw.strip()
        if not raw:
            continue
        lines.append(raw)
    for raw in lines:
        m = re.fullmatch(r"([a-zA-Z_][\w.]*):", raw)
        if m:
            labels[m.group(1)] = pc
            continue
        m = re.fullmatch(r"\.align\s+(\d+)", raw)
        if m:
            a = 1 << int(m.group(1))
            if pc % a:
                pc += a - pc % a
            continue
        m = re.fullmatch(r"\.org\s+(\S+)", raw)
        if m:
            pc = num(m.group(1), labels, pc)
            continue
        m = re.fullmatch(r"\.word\s+(\S+)", raw)
        if m:
            pc += 4
            continue
        pc += 4
    globals_labels = labels
    lines = expand_li(lines)
    # recompute labels after expansion
    labels = {}
    pc = 0
    for raw in lines:
        m = re.fullmatch(r"([a-zA-Z_][\w.]*):", raw)
        if m:
            labels[m.group(1)] = pc
            continue
        m = re.fullmatch(r"\.align\s+(\d+)", raw)
        if m:
            a = 1 << int(m.group(1))
            if pc % a:
                pc += a - pc % a
            continue
        m = re.fullmatch(r"\.org\s+(\S+)", raw)
        if m:
            pc = num(m.group(1), labels, pc)
            continue
        m = re.fullmatch(r"\.word\s+(\S+)", raw)
        if m:
            pc += 4
            continue
        m = re.fullmatch(r"call\s+(\S+)", raw)
        if m:
            pc += 8
            continue
        pc += 4
    globals_labels = labels
    # pass 2: encode (iterate until stable to resolve forward refs)
    out = {}
    for _round in range(8):
        out = {}
        pc = 0
        changed = False
        for raw in lines:
            cur_pc = pc
            m = re.fullmatch(r"([a-zA-Z_][\w.]*):", raw)
            if m:
                # recompute labels every round: pseudo-expansions shift addresses
                if labels.get(m.group(1)) != pc:
                    labels[m.group(1)] = pc
                    changed = True
                continue
            m = re.fullmatch(r"\.align\s+(\d+)", raw)
            if m:
                a = 1 << int(m.group(1))
                if pc % a:
                    pc += a - pc % a
                continue
            m = re.fullmatch(r"\.org\s+(\S+)", raw)
            if m:
                pc = num(m.group(1), labels, pc)
                continue
            m = re.fullmatch(r"\.word\s+(\S+)", raw)
            if m:
                try:
                    v = num(m.group(1), labels, pc)
                except ValueError:
                    v = 0
                if out.get(pc) != (v & 0xFFFFFFFF):
                    changed = True
                out[pc] = v & 0xFFFFFFFF
                pc += 4
                continue
            m = re.fullmatch(r"call\s+(\S+)", raw)
            if m:
                try:
                    d = num(m.group(1), labels, pc) - pc
                    chk(d, -1048576, 1048575, "jimm")
                    w0 = enc_j(0x6F, 1, d)
                    w1 = enc_i(0x13, 0, 2, 2, 0)
                except ValueError:
                    changed = True
                    w0 = out.get(pc, 0)
                    w1 = out.get(pc + 4, 0)
                if out.get(pc) != w0 or out.get(pc + 4) != w1:
                    changed = True
                out[pc] = w0
                out[pc + 4] = w1
                pc += 8
                continue
            m = re.fullmatch(r"la\s+([-\w]+)\s*,\s*(\S+)", raw)
            if m:
                # GNU semantics: auipc + addi, pc-relative to the auipc
                try:
                    d = num(m.group(2), labels, pc) - pc
                    hi = (d + 0x800) >> 12
                    lo = d - (hi << 12)
                    chk(hi, -1048576, 1048575, "auipc")
                    chk(lo, -2048, 2047, "imm")
                    w0 = enc_u(AU, reg(m.group(1)), hi << 12)
                    w1 = enc_i(0x13, 0, reg(m.group(1)), reg(m.group(1)), lo)
                except ValueError:
                    changed = True
                    w0 = out.get(pc, 0)
                    w1 = out.get(pc + 4, 0)
                if out.get(pc) != w0 or out.get(pc + 4) != w1:
                    changed = True
                out[pc] = w0
                out[pc + 4] = w1
                pc += 8
                continue
            try:
                w = encode(raw, labels, pc)
            except ValueError as e:
                if "unknown symbol" in str(e):
                    w = 0
                else:
                    raise
            if out.get(pc) != w:
                changed = True
            out[pc] = w
            pc += 4
        if not changed:
            break
    if not out:
        return b""
    top = 0
    trace = []
    for a in sorted(out):
        v = out[a]
        if v >= (1 << 64):
            trace.append(((v >> 32) & 0xFFFFFFFF, (v >> 5) & 31, v & 0xFFFFFFFF))
        else:
            top = max(top, a + 4)
    img = bytearray(max(top, 4))
    for a in sorted(out):
        v = out[a]
        if v < (1 << 64) and a + 4 <= len(img):
            img[a:a+4] = v.to_bytes(4, "little")
    assemble.trace = sorted(trace)
    return bytes(img)

def split_top(s):
    # split on commas outside parentheses and braces
    parts, depth, cur = [], 0, ""
    for ch in s:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur); cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p for p in parts]


def split_args(s):
    # split on commas outside parentheses
    parts, depth, cur = [], 0, ""
    for ch in s:
        if ch == "(":
            depth += 1
        if ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur); cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p for p in parts]

def encode(line, labels, pc):
    # trace directive: .word {pc, rd, wdata}
    m = re.fullmatch(r"trace\s+\{(.*)\}", line)
    if m:
        pcv, rdv, wv = [num(x, labels, pc) for x in split_top(m.group(1))]
        return (1 << 64) | (wv & 0xFFFFFFFF) << 32 | (rdv & 31) << 5 | (pcv & 0xFFFFFFFF)
    m = re.fullmatch(r"([a-zA-Z][\w.%$]*|f[0-7])\s*(.*)", line)
    if not m:
        raise ValueError(f"bad line: {line}")
    mn, argstr = m.group(1).lower(), m.group(2).strip()
    args = split_args(argstr) if argstr else []
    args = [a.strip() for a in args]


    def imm(t):
        v = num(t, labels, pc)
        chk(v, -2048, 2047, "imm")
        return v

    def jimm(t):
        v = num(t, labels, pc) - pc
        chk(v, -1048576, 1048575, "jimm")
        return v

    def bimm(t):
        v = num(t, labels, pc) - pc
        chk(v, -4096, 4095, "bimm")
        if v & 1:
            raise ValueError("branch offset must be even")
        return v

    I = 0x33; II = 0x13; L = 0x03; S = 0x23; BR = 0x63; LU = 0x37; AU = 0x17
    J = 0x6F; JR = 0x67; SYS = 0x73

    alu_i = {"addi":0,"slti":2,"sltiu":3,"xori":4,"ori":6,"andi":7}
    alu_r = {"add":0,"slt":2,"sltu":3,"xor":4,"or":6,"and":7}
    shifts_i = {"slli":(1,0),"srli":(5,0),"srai":(5,0x20)}
    shifts_r = {"sll":(1,0),"srl":(5,0),"sra":(5,0x20)}
    loads = {"lb":0,"lh":1,"lw":2,"lbu":4,"lhu":5}
    stores = {"sb":0,"sh":1,"sw":2}
    branches = {"beq":0,"bne":1,"blt":4,"bge":5,"bltu":6,"bgeu":7}
    csrs = {"csrrw":1,"csrrs":2,"csrrc":3,"csrrwi":5,"csrrsi":6,"csrrci":7}

    def csr_addr(t):
        names = {"mtvec":0x305,"mscratch":0x340,"mepc":0x341,"mcause":0x342,
                 "mvendorid":0xF11,"misa":0x301,"mhartid":0x14E}
        t = t.strip()
        if t in names:
            return names[t]
        return num(t, labels, pc)

    if mn in alu_i:
        return enc_i(II, alu_i[mn], reg(args[0]), reg(args[1]), imm(args[2]))
    if mn == "li":
        raise ValueError("li must be expanded by pre-pass")
    if mn == "mv":
        return enc_i(II, 0, reg(args[0]), reg(args[1]), 0)
    if mn == "not":
        return enc_i(II, 4, reg(args[0]), reg(args[1]), -1)
    if mn in shifts_i:
        f3, f7b = shifts_i[mn]
        sh = num(args[2], labels, pc)
        chk(sh, 0, 31, "shamt")
        return enc_i(II, f3, reg(args[0]), reg(args[1]), sh | (f7b << 5))
    if mn in alu_r:
        return I | (alu_r[mn] << 12) | (reg(args[0]) << 7) | (reg(args[1]) << 15) | (reg(args[2]) << 20)
    if mn == "sub":
        return I | (0 << 12) | (reg(args[0]) << 7) | (reg(args[1]) << 15) | (reg(args[2]) << 20) | (0x20 << 25)
    if mn in shifts_r:
        f3, f7b = shifts_r[mn]
        return I | (f3 << 12) | (reg(args[0]) << 7) | (reg(args[1]) << 15) | (reg(args[2]) << 20) | (f7b << 25)
    if mn in loads:
        off, base = parse_mem(args[1])
        chk(off, -2048, 2047, "ld-off")
        return enc_i(L, loads[mn], reg(args[0]), base, off)
    if mn in stores:
        off, base = parse_mem(args[1])
        chk(off, -2048, 2047, "st-off")
        return enc_s(S, stores[mn], base, reg(args[0]), off)
    if mn in branches:
        return enc_b(BR, branches[mn], reg(args[0]), reg(args[1]), bimm(args[2]))
    if mn == "beqz":
        return enc_b(BR, 0, reg(args[0]), 0, bimm(args[1]))
    if mn == "bnez":
        return enc_b(BR, 1, reg(args[0]), 0, bimm(args[1]))
    if mn == "lui":
        v = num(args[1], labels, pc)
        chk(v, -1048576, 1048575, "lui")
        return enc_u(LU, reg(args[0]), v << 12)
    if mn == "auipc":
        v = num(args[1], labels, pc)
        chk(v, -1048576, 1048575, "auipc")
        return enc_u(AU, reg(args[0]), v << 12)
    if mn == "jal":
        if len(args) == 1:
            return enc_j(J, 1, jimm(args[0]))
        return enc_j(J, reg(args[0]), jimm(args[1]))
    if mn == "jalr":
        if len(args) == 1:
            return enc_i(JR, 0, 1, reg(args[0]), 0)
        if len(args) == 2:
            return enc_i(JR, 0, reg(args[0]), reg(args[1]), 0)
        if argstr.count(",") >= 2:  # rd, rs1, imm
            off = num(args[2], labels, pc)
            chk(off, -2048, 2047, "imm")
            return enc_i(JR, 0, reg(args[0]), reg(args[1]), off)
        off, base = parse_mem(args[1])
        return enc_i(JR, 0, reg(args[0]), base, off)
    if mn == "j":
        return enc_j(J, 0, jimm(args[0]))
    if mn == "ret":
        return enc_i(JR, 0, 0, 1, 0)
    if mn in ("csrrw", "csrrs", "csrrc"):
        # GNU syntax: csrrw rd, csr, rs1
        f3 = csrs[mn]
        csr = csr_addr(args[1])
        chk(csr, 0, 0xFFF, "csr")
        return enc_i(SYS, f3, reg(args[0]), reg(args[2]), csr)
    if mn == "csrw":  # csrw csr, rs -> csrrw x0, csr, rs
        csr = csr_addr(args[0])
        return enc_i(SYS, 1, 0, reg(args[1]), csr)
    if mn == "csrr":  # csrr rd, csr -> csrrs rd, csr, x0
        csr = csr_addr(args[1])
        return enc_i(SYS, 2, reg(args[0]), 0, csr)
    if mn == "csrrwi":  # csrrwi rd, csr, zimm
        rd = reg(args[0])
        csr = csr_addr(args[1])
        u = num(args[2], labels, pc)
        chk(u, 0, 31, "zimm")
        return enc_i(SYS, 5, rd, u, csr)
    if mn == "csrrsi":  # csrrsi rd, csr, zimm
        rd = reg(args[0])
        csr = csr_addr(args[1])
        u = num(args[2], labels, pc)
        chk(u, 0, 31, "zimm")
        return enc_i(SYS, 6, rd, u, csr)
    if mn == "csrrci":  # csrrci rd, csr, zimm
        rd = reg(args[0])
        csr = csr_addr(args[1])
        u = num(args[2], labels, pc)
        chk(u, 0, 31, "zimm")
        return enc_i(SYS, 7, rd, u, csr)
    if mn == "ecall":
        return 0x73
    if mn == "ebreak":
        return 0x00100073
    if mn == "mret":
        return 0x30200073
    if mn == "fence":
        return 0x0FF0000F
    if mn == "nop":
        return enc_i(II, 0, 0, 0, 0)
    raise ValueError(f"unknown mnemonic: {mn}")

if __name__ == "__main__":
    src = open(sys.argv[1]).read()
    data = assemble(src)
    open(sys.argv[2], "wb").write(data)
    # also dump a hex file ($readmemh format: one word per line)
    if len(sys.argv) > 3:
        with open(sys.argv[3], "w") as f:
            for i in range(0, len(data), 4):
                f.write(data[i:i+4][::-1].hex() + "\n")
