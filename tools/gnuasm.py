#!/usr/bin/env python3
"""
Thin wrapper around the authoritative GNU RISC-V toolchain
(riscv64-linux-gnu-as / -ld / -objcopy from binutils-riscv64-linux-gnu).

assemble_file(path) -> bytes   flat little-endian image loaded at address 0
Used by the golden ISS and the Veryl test generator so the expected
traces are produced from GNU-assembled encodings.
"""
import os, subprocess, tempfile

AS      = "riscv64-linux-gnu-as"
LD      = "riscv64-linux-gnu-ld"
OBJCOPY = "riscv64-linux-gnu-objcopy"
OBJDUMP = "riscv64-linux-gnu-objdump"

LINKER_SCRIPT = """
SECTIONS {
  . = BASE_ADDR;
  .text : { *(.text .text.*) }
  .data : { *(.data .data.*) *(.sdata .sdata.*) }
  .rodata : { *(.rodata .rodata.*) *(.srodata .srodata.*) }
}
"""

def assemble_file(path, base=0x80000000):
    with tempfile.TemporaryDirectory() as td:
        o    = os.path.join(td, "x.o")
        elf  = os.path.join(td, "x.elf")
        binf = os.path.join(td, "x.bin")
        ldscript = os.path.join(td, "x.ld")
        with open(ldscript, "w") as f:
            f.write(LINKER_SCRIPT.replace("BASE_ADDR", hex(base)))
        subprocess.run([AS, "-march=rv32i_zicsr", "-mabi=ilp32",
                        "-o", o, path], check=True)
        subprocess.run([LD, "-m", "elf32lriscv", "-T", ldscript,
                        "-o", elf, o], check=True)
        subprocess.run([OBJCOPY, "-O", "binary", elf, binf], check=True)
        return open(binf, "rb").read()

def link_elf(path, elf_out, base=0x80000000):
    """Assemble + link into an ELF at the given base (for Spike)."""
    with tempfile.TemporaryDirectory() as td:
        o = os.path.join(td, "x.o")
        ldscript = os.path.join(td, "x.ld")
        with open(ldscript, "w") as f:
            f.write(LINKER_SCRIPT.replace("BASE_ADDR", hex(base)))
        subprocess.run([AS, "-march=rv32i_zicsr", "-mabi=ilp32",
                        "-o", o, path], check=True)
        subprocess.run([LD, "-m", "elf32lriscv", "-T", ldscript,
                        "-o", elf_out, o], check=True)

def text_top(path, base=0x80000000):
    """VMA end of the .text section for the linked program."""
    import re
    with tempfile.TemporaryDirectory() as td:
        elf = os.path.join(td, "x.elf")
        link_elf(path, elf, base)
        out = subprocess.run([OBJDUMP, "-h", elf],
                             capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        m = re.match(r"\s*\d+\s+\.text\s+([0-9a-f]+)\s+([0-9a-f]+)", line)
        if m:
            return int(m.group(1), 16) + int(m.group(2), 16)
    return None

def disassemble_file(path, base=0x80000000):
    """Return {addr: word} for the linked program (for cross checks)."""
    with tempfile.TemporaryDirectory() as td:
        elf = os.path.join(td, "x.elf")
        link_elf(path, elf, base)
        out = subprocess.run([OBJDUMP, "-d", "--show-raw-insn", elf],
                             capture_output=True, text=True, check=True).stdout
    import re
    words = {}
    for line in out.splitlines():
        m = re.match(r"\s+([0-9a-f]+):\s+([0-9a-f]{8})\s", line)
        if m:
            words[int(m.group(1), 16)] = int(m.group(2), 16)
    return words

if __name__ == "__main__":
    import sys
    data = assemble_file(sys.argv[1])
    open(sys.argv[2], "wb").write(data)
    print(f"{sys.argv[1]} -> {sys.argv[2]} ({len(data)} bytes)")
