# RV32I branches: all 6 conditions, taken and not-taken
main:
    li   x1, 5
    li   x2, 5
    li   x3, -3
    li   x4, 2

    beq  x1, x2, t1              # taken
    li   x10, 0                  # skipped
t1:
    bne  x1, x2, s1              # not taken
    li   x10, 11                 # executed
s1:
    blt  x3, x4, t2              # taken (signed)
    li   x10, 0
t2:
    bge  x4, x3, t3              # taken
    li   x10, 0
t3:
    bltu x4, x3, s2              # not taken (unsigned: 2 < 0xffff_fffd false)
    li   x10, 22
s2:
    bgeu x3, x4, s3              # taken (unsigned big)
    li   x10, 0
s3:
    beq  x1, x3, s4              # not taken
    li   x10, 33
s4:
    # backward branch loop: count 4 down to 0
    li   x5, 4
    li   x6, 0
loop:
    addi x6, x6, 1
    addi x5, x5, -1
    bne  x5, x0, loop            # backward taken branch x4 times
    add  x11, x6, x0             # x11 = 4
    ebreak
loop2:
    j loop2
