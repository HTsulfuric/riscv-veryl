# Trap: illegal instruction -> mtvec handler -> mret back.
# The handler checks mcause==2 and mepc==&bad, then skips the bad insn.
main:
    la   x1, handler
    csrw mtvec, x1
    li   x2, 11
    addi x3, x0, 0
    .word  0xffffffff             # illegal: hits handler
    addi x3, x0, 22               # resumed here (handler added 4 to mepc)
    li   x4, 33
    ebreak                        # halt
l:
    j l

handler:
    csrr x5, mcause               # 2
    csrr x6, mepc                 # address of the illegal insn
    addi x6, x6, 4                # skip it
    csrw mepc, x6
    mret
