# RV32I jumps: jal link/offset, jal rd=x0 (no link), jalr return, recursion
main:
    la   x2, stack_top           # stack top (position-independent, grows down)
    jal  x1, leaf                # x1 = main + 8
    add  x10, x0, a0             # x10 = 7
    li   a0, 4
    jal  ra, sum                   # a0 = 4+3+2+1 = 10
    add  x11, x0, a0             # x11 = 10
    li   x1, 0x1234              # sentinel link value
    jal  x0, dead                # rd=x0: must NOT write the link
cont:
    add  x12, x0, x1             # x12 = 0x1234 proves x1 untouched
    ebreak
m2:
    j m2

# leaf: a0 = 7, return via ra
leaf:
    addi a0, x0, 7
    jalr x0, ra, 0
    addi a0, x0, 99              # skipped

# sum(n): a0 = n==0 ? 0 : n + sum(n-1);  a1 is scratch (holds n during rec)
sum:
    addi sp, sp, -8
    sw   ra, 0(sp)
    bne  a0, x0, rec
    add  a0, x0, x0
    j    ret
rec:
    addi a1, a0, 0               # a1 = n
    addi a0, a0, -1
    jal  ra, sum                 # a0 = sum(n-1)
    add  a0, a1, a0              # a0 = n + sum(n-1)
ret:
    lw   ra, 0(sp)
    addi sp, sp, 8
    jalr x0, ra, 0

dead:
    addi x13, x0, 1              # side effect only
    jal  x0, cont                # explicit forward return

    .section .data
    .align 4
    .space 0x400
stack_top:
